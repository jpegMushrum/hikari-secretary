from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from ..access import AdminAccess
from ..keyboards import (
    admin_ai_menu_keyboard,
    ai_comment_cancel_keyboard,
    ai_revision_cancel_keyboard,
    ai_topic_preview_keyboard,
    queue_cancel_keyboard,
)
from ..formatting import rich_message_from_json
from ..repositories.daily_topics import DailyTopicRepository
from ..runtime import AiTopicPreview, AppContext
from ..services.daily_topics import DailyTopicService, TopicGenerationOptions


log = logging.getLogger(__name__)


class AiTopicHandlers:
    def __init__(
        self,
        context: AppContext,
        access: AdminAccess,
        service: DailyTopicService | None,
        repository: DailyTopicRepository,
    ):
        self.context = context
        self.access = access
        self.service = service
        self.repository = repository

    def register(self, router: Router) -> None:
        router.callback_query.register(self.menu, F.data == "admin_ai_menu")
        router.callback_query.register(
            self.set_level, F.data.startswith("ai_level:")
        )
        router.callback_query.register(
            self.request_comment, F.data == "ai_comment_request"
        )
        router.callback_query.register(
            self.clear_comment, F.data == "ai_comment_clear"
        )
        router.callback_query.register(
            self.cancel_comment, F.data == "ai_comment_cancel"
        )
        router.callback_query.register(self.generate, F.data == "ai_generate")
        router.callback_query.register(
            self.regenerate, F.data == "ai_regenerate"
        )
        router.callback_query.register(self.publish, F.data == "ai_publish")
        router.callback_query.register(self.cancel, F.data == "ai_cancel")
        router.callback_query.register(
            self.queue_preview, F.data.startswith("ai_queue_preview:")
        )
        router.callback_query.register(
            self.queue_regenerate, F.data.startswith("ai_queue_regenerate:")
        )
        router.callback_query.register(
            self.queue_revise, F.data.startswith("ai_queue_revise:")
        )
        router.callback_query.register(
            self.cancel_queue_revision,
            F.data.startswith("ai_queue_revision_cancel:"),
        )

    async def menu(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        await self._show_menu(callback.message.edit_text, callback.from_user.id)
        await callback.answer()

    def _keyboard(self, options: TopicGenerationOptions):
        return admin_ai_menu_keyboard(
            self.service is not None,
            options.jlpt_level,
            options.admin_comment is not None,
        )

    async def _show_menu(self, send, admin_id: int) -> None:
        settings = self.context.settings.ai_topics
        options = await self.repository.preferences()
        if self.service and settings.target:
            target = settings.target.name
            state = "готов к работе"
        else:
            target = "не задан"
            state = "не настроен: укажите DEEPSEEK_API_KEY и AI_TOPIC_TARGET_KEY"
        auto_publish = (
            f"ежедневно в {settings.auto_publish_time:%H:%M} "
            f"({self.context.settings.timezone_name})"
            if settings.auto_publish_time else "отключена"
        )
        await send(
            "🤖 ИИ-материалы\n\n"
            f"Состояние: {state}\n"
            f"Цель: {target}\n"
            f"Автопубликация: {auto_publish}\n"
            f"Уровень текущей генерации: JLPT {options.jlpt_level}\n"
            f"Вопросов: {settings.question_count}\n"
            f"Слов: {settings.vocabulary_count}\n"
            f"Грамматических конструкций: {settings.grammar_count}\n"
            f"Комментарий администратора: {options.admin_comment or 'нет'}",
            reply_markup=self._keyboard(options),
        )

    async def set_level(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        level = callback.data.partition(":")[2]
        if level not in {"N5", "N4", "N3", "N2", "N1"}:
            await callback.answer("Некорректный уровень", show_alert=True)
            return
        options = await self.repository.preferences()
        await self.repository.save_preferences(
            TopicGenerationOptions(level, options.admin_comment),
            callback.from_user.id,
        )
        await self._show_menu(callback.message.edit_text, callback.from_user.id)
        await callback.answer(f"Выбран JLPT {level}")

    async def request_comment(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        self.context.state.awaiting_ai_comment.add(callback.from_user.id)
        await callback.message.answer(
            "Напишите пожелание к теме одним сообщением — например, предложите "
            "конкретную тему или направление. Максимум 500 символов.",
            reply_markup=ai_comment_cancel_keyboard(),
        )
        await callback.answer()

    async def cancel_comment(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        self.context.state.awaiting_ai_comment.discard(callback.from_user.id)
        await self._show_menu(callback.message.edit_text, callback.from_user.id)
        await callback.answer("Ввод комментария отменён")

    async def clear_comment(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        options = await self.repository.preferences()
        await self.repository.save_preferences(
            TopicGenerationOptions(options.jlpt_level, None),
            callback.from_user.id,
        )
        self.context.state.awaiting_ai_comment.discard(callback.from_user.id)
        await self._show_menu(callback.message.edit_text, callback.from_user.id)
        await callback.answer("Комментарий удалён")

    async def handle_text_flow(self, message: Message) -> bool:
        if (
            not message.from_user
            or message.chat.type != "private"
            or not self.access.is_admin(message.from_user.id)
        ):
            return False
        comment = " ".join((message.text or "").strip().split())
        revision_post_id = self.context.state.awaiting_ai_revision.get(
            message.from_user.id
        )
        if revision_post_id is not None:
            if not comment:
                await message.answer("Пожелание не должно быть пустым.")
                return True
            if len(comment) > 500:
                await message.answer("Пожелание слишком длинное. Максимум 500 символов.")
                return True
            self.context.state.awaiting_ai_revision.pop(message.from_user.id, None)
            status = await message.answer("⏳ Исправляю запланированную тему…")
            await self._replace_queued_topic(
                revision_post_id,
                message.from_user.id,
                status,
                revision=comment,
            )
            return True
        if message.from_user.id not in self.context.state.awaiting_ai_comment:
            return False
        if not comment:
            await message.answer("Комментарий не должен быть пустым.")
            return True
        if len(comment) > 500:
            await message.answer("Комментарий слишком длинный. Максимум 500 символов.")
            return True
        options = await self.repository.preferences()
        await self.repository.save_preferences(
            TopicGenerationOptions(options.jlpt_level, comment),
            message.from_user.id,
        )
        self.context.state.awaiting_ai_comment.discard(message.from_user.id)
        await self._show_menu(message.answer, message.from_user.id)
        return True

    async def generate(self, callback: CallbackQuery) -> None:
        await self._generate(callback)

    async def regenerate(self, callback: CallbackQuery) -> None:
        await self._generate(callback)

    async def _generate(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        if not self.service:
            await callback.answer("ИИ-сервис не настроен", show_alert=True)
            return
        await callback.answer("Генерирую тему…")
        status = await callback.message.answer(
            "⏳ Генерирую материал. Это может занять некоторое время."
        )
        try:
            history = await self.repository.recent_history()
            options = await self.repository.preferences()
            topic = await self.service.generate(
                history, options,
            )
        except Exception:
            log.exception(
                "AI topic preview generation failed: admin_id=%s",
                callback.from_user.id,
            )
            await status.edit_text(
                "Не удалось сгенерировать тему. Проверьте настройки и логи, "
                "затем попробуйте ещё раз.",
                reply_markup=self._keyboard(await self.repository.preferences()),
            )
            return
        self.context.state.ai_topic_previews[callback.from_user.id] = (
            AiTopicPreview(uuid.uuid4().hex, topic)
        )
        await self.context.bot.send_rich_message(
            callback.message.chat.id,
            rich_message_from_json(self.service.renderer.rich_message(topic)),
        )
        await status.edit_text(
            "Предпросмотр ИИ-публикации. Выберите действие:",
            reply_markup=ai_topic_preview_keyboard(),
        )
        log.info(
            "AI topic preview generated: admin_id=%s title=%r history_size=%s",
            callback.from_user.id,
            topic.title,
            len(history),
        )

    async def publish(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        if not self.service:
            await callback.answer("ИИ-сервис не настроен", show_alert=True)
            return
        preview = self.context.state.ai_topic_previews.get(callback.from_user.id)
        if not preview:
            await callback.answer(
                "Предпросмотр устарел. Сгенерируйте тему заново.", show_alert=True
            )
            return
        try:
            post_id = await self.service.schedule(
                preview.topic,
                creator_id=callback.from_user.id,
                scheduled_at=datetime.now(timezone.utc),
                idempotency_key=f"ai-admin:{preview.token}",
            )
        except Exception:
            log.exception(
                "AI topic publication failed: admin_id=%s",
                callback.from_user.id,
            )
            await callback.answer("Не удалось поставить публикацию в очередь", show_alert=True)
            return

        history_saved = True
        try:
            await self.repository.record_manual_publication(
                post_id, preview.topic.as_json_value()
            )
        except Exception:
            history_saved = False
            log.exception(
                "AI topic was scheduled but history was not saved: post_id=%s",
                post_id,
            )
        self.context.state.ai_topic_previews.pop(callback.from_user.id, None)
        options = await self.repository.preferences()
        suffix = "" if history_saved else "\n⚠️ Не удалось сохранить тему в историю."
        await callback.message.edit_text(
            f"✅ ИИ-публикация #{post_id} поставлена в очередь.{suffix}",
            reply_markup=self._keyboard(options),
        )
        await callback.answer()
        log.info(
            "AI topic publication scheduled: admin_id=%s post_id=%s history_saved=%s",
            callback.from_user.id,
            post_id,
            history_saved,
        )

    async def queue_preview(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        post_id = int(callback.data.rsplit(":", 1)[1])
        post = await self.context.db.post(post_id)
        if not self._is_editable_ai_post(post):
            await callback.answer("Публикация уже недоступна", show_alert=True)
            return
        await self.context.bot.send_rich_message(
            callback.message.chat.id,
            rich_message_from_json(post["rich_message"]),
        )
        await callback.answer()

    async def queue_regenerate(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        post_id = int(callback.data.rsplit(":", 1)[1])
        await callback.answer("Перегенерирую тему…")
        status = await callback.message.answer("⏳ Перегенерирую публикацию…")
        await self._replace_queued_topic(post_id, callback.from_user.id, status)

    async def queue_revise(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        post_id = int(callback.data.rsplit(":", 1)[1])
        post = await self.context.db.post(post_id)
        if not self._is_editable_ai_post(post):
            await callback.answer("Публикация уже недоступна", show_alert=True)
            return
        self.context.state.awaiting_ai_comment.discard(callback.from_user.id)
        self.context.state.awaiting_ai_revision[callback.from_user.id] = post_id
        await callback.message.answer(
            "Напишите, что нужно исправить в этой публикации. Бот заново "
            "сгенерирует материал с учётом замечания, сохранив время публикации.",
            reply_markup=ai_revision_cancel_keyboard(post_id),
        )
        await callback.answer()

    async def cancel_queue_revision(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        post_id = int(callback.data.rsplit(":", 1)[1])
        self.context.state.awaiting_ai_revision.pop(callback.from_user.id, None)
        await callback.message.edit_text(
            "Исправление отменено.",
            reply_markup=queue_cancel_keyboard(post_id, True),
        )
        await callback.answer()

    async def _replace_queued_topic(
        self,
        post_id: int,
        admin_id: int,
        status: Message,
        *,
        revision: str | None = None,
    ) -> None:
        if not self.service:
            await status.edit_text("ИИ-сервис не настроен.")
            return
        post = await self.context.db.post(post_id)
        if not self._is_editable_ai_post(post):
            await status.edit_text("Публикация уже вышла или была отменена.")
            return
        try:
            options = await self.repository.preferences()
            if revision:
                parts = [value for value in (options.admin_comment, revision) if value]
                options = TopicGenerationOptions(
                    options.jlpt_level, "\n".join(parts)
                )
            history = await self.repository.recent_history(
                exclude_post_id=post_id
            )
            topic = await self.service.generate(history, options)
            if not await self.service.replace_scheduled(post_id, topic):
                raise RuntimeError("Публикация больше не доступна для изменения")
            if not await self.repository.replace_topic_for_post(
                post_id, topic.as_json_value()
            ):
                raise RuntimeError("Не найдена история AI-публикации")
        except Exception:
            log.exception(
                "Queued AI topic replacement failed: post_id=%s admin_id=%s",
                post_id,
                admin_id,
            )
            await status.edit_text(
                "Не удалось обновить публикацию. Проверьте логи и попробуйте ещё раз.",
                reply_markup=queue_cancel_keyboard(post_id, True),
            )
            return
        await self.context.bot.send_rich_message(
            admin_id, rich_message_from_json(self.service.renderer.rich_message(topic))
        )
        await status.edit_text(
            f"✅ Публикация #{post_id} обновлена. Время публикации сохранено.",
            reply_markup=queue_cancel_keyboard(post_id, True),
        )

    @staticmethod
    def _is_editable_ai_post(post: dict | None) -> bool:
        return bool(
            post
            and post["status"] == "scheduled"
            and post["source"] == "ai_daily_topic"
            and post["rich_message"]
        )

    async def cancel(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        self.context.state.ai_topic_previews.pop(callback.from_user.id, None)
        options = await self.repository.preferences()
        self.context.state.awaiting_ai_comment.discard(callback.from_user.id)
        await callback.message.edit_text(
            "Генерация отменена. Тема не опубликована и не добавлена в историю.",
            reply_markup=self._keyboard(options),
        )
        await callback.answer()
