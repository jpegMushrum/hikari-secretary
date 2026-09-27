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
    ai_topic_preview_keyboard,
)
from ..repositories.daily_topics import DailyTopicRepository
from ..runtime import AiTopicAdminOptions, AiTopicPreview, AppContext
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

    async def menu(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        await self._show_menu(callback.message.edit_text, callback.from_user.id)
        await callback.answer()

    def _options(self, admin_id: int) -> AiTopicAdminOptions:
        return self.context.state.ai_topic_options.setdefault(
            admin_id, AiTopicAdminOptions("N3")
        )

    def _keyboard(self, admin_id: int):
        options = self._options(admin_id)
        return admin_ai_menu_keyboard(
            self.service is not None,
            options.jlpt_level,
            options.comment is not None,
        )

    async def _show_menu(self, send, admin_id: int) -> None:
        settings = self.context.settings.ai_topics
        options = self._options(admin_id)
        if self.service and settings.target:
            target = settings.target.name
            state = "готов к работе"
        else:
            target = "не задан"
            state = "не настроен: укажите DEEPSEEK_API_KEY и AI_TOPIC_TARGET_KEY"
        await send(
            "🤖 ИИ-материалы\n\n"
            f"Состояние: {state}\n"
            f"Цель: {target}\n"
            f"Уровень текущей генерации: JLPT {options.jlpt_level}\n"
            f"Вопросов: {settings.question_count}\n"
            f"Слов: {settings.vocabulary_count}\n"
            f"Грамматических конструкций: {settings.grammar_count}\n"
            f"Комментарий администратора: {options.comment or 'нет'}",
            reply_markup=self._keyboard(admin_id),
        )

    async def set_level(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        level = callback.data.partition(":")[2]
        if level not in {"N5", "N4", "N3", "N2", "N1"}:
            await callback.answer("Некорректный уровень", show_alert=True)
            return
        self._options(callback.from_user.id).jlpt_level = level
        await self._show_menu(callback.message.edit_text, callback.from_user.id)
        await callback.answer(f"Выбран JLPT {level}")

    async def request_comment(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        self._options(callback.from_user.id).awaiting_comment = True
        await callback.message.answer(
            "Напишите пожелание к теме одним сообщением — например, предложите "
            "конкретную тему или направление. Максимум 500 символов.",
            reply_markup=ai_comment_cancel_keyboard(),
        )
        await callback.answer()

    async def cancel_comment(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        self._options(callback.from_user.id).awaiting_comment = False
        await self._show_menu(callback.message.edit_text, callback.from_user.id)
        await callback.answer("Ввод комментария отменён")

    async def clear_comment(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        options = self._options(callback.from_user.id)
        options.comment = None
        options.awaiting_comment = False
        await self._show_menu(callback.message.edit_text, callback.from_user.id)
        await callback.answer("Комментарий удалён")

    async def handle_text_flow(self, message: Message) -> bool:
        if (
            not message.from_user
            or message.chat.type != "private"
            or not self.access.is_admin(message.from_user.id)
        ):
            return False
        options = self.context.state.ai_topic_options.get(message.from_user.id)
        if not options or not options.awaiting_comment:
            return False
        comment = " ".join((message.text or "").strip().split())
        if not comment:
            await message.answer("Комментарий не должен быть пустым.")
            return True
        if len(comment) > 500:
            await message.answer("Комментарий слишком длинный. Максимум 500 символов.")
            return True
        options.comment = comment
        options.awaiting_comment = False
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
            options = self._options(callback.from_user.id)
            topic = await self.service.generate(
                history,
                TopicGenerationOptions(options.jlpt_level, options.comment),
            )
        except Exception:
            log.exception(
                "AI topic preview generation failed: admin_id=%s",
                callback.from_user.id,
            )
            await status.edit_text(
                "Не удалось сгенерировать тему. Проверьте настройки и логи, "
                "затем попробуйте ещё раз.",
                reply_markup=self._keyboard(callback.from_user.id),
            )
            return
        self.context.state.ai_topic_previews[callback.from_user.id] = (
            AiTopicPreview(uuid.uuid4().hex, topic)
        )
        await status.edit_text(
            self.service.renderer.render(topic),
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
        self._options(callback.from_user.id).comment = None
        suffix = "" if history_saved else "\n⚠️ Не удалось сохранить тему в историю."
        await callback.message.edit_text(
            f"✅ ИИ-публикация #{post_id} поставлена в очередь.{suffix}",
            reply_markup=self._keyboard(callback.from_user.id),
        )
        await callback.answer()
        log.info(
            "AI topic publication scheduled: admin_id=%s post_id=%s history_saved=%s",
            callback.from_user.id,
            post_id,
            history_saved,
        )

    async def cancel(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        self.context.state.ai_topic_previews.pop(callback.from_user.id, None)
        options = self._options(callback.from_user.id)
        options.comment = None
        options.awaiting_comment = False
        await callback.message.edit_text(
            "Генерация отменена. Тема не опубликована и не добавлена в историю.",
            reply_markup=self._keyboard(callback.from_user.id),
        )
        await callback.answer()
