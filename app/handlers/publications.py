from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..access import AdminAccess
from ..formatting import (
    entities_to_json,
    format_local,
    parse_schedule,
    rich_message_from_json,
    rich_message_preview,
    rich_message_to_json,
)
from ..keyboards import draft_keyboard, queue_cancel_keyboard
from ..presentation import remove_media
from ..runtime import AlbumBuffer, AppContext, EventSetup

log = logging.getLogger(__name__)


class PublicationHandlers:
    def __init__(
        self,
        context: AppContext,
        access: AdminAccess,
    ):
        self.context = context
        self.access = access

    def register(self, router: Router) -> None:
        router.message.register(self.queue, Command("queue"))
        router.callback_query.register(self.toggle_target, F.data.startswith("target:"))
        router.callback_query.register(self.toggle_event, F.data.startswith("event:"))
        router.callback_query.register(self.publish_now, F.data.startswith("now:"))
        router.callback_query.register(self.ask_schedule, F.data.startswith("schedule:"))
        router.callback_query.register(self.cancel, F.data.startswith("cancel:"))

    async def queue(self, message: Message) -> None:
        if not await self.access.guard_message(message):
            return
        rows = await self.context.db.queue()
        if not rows:
            await message.answer("Очередь пуста.")
            return
        for row in rows:
            await message.answer(
                f"Публикация #{row['id']}\n"
                f"Время: {format_local(row['scheduled_at'], self.context.settings.timezone)} "
                f"({self.context.settings.timezone_name})\n"
                f"Цели: {row['targets']}",
                reply_markup=queue_cancel_keyboard(row["id"]),
            )

    async def content(self, message: Message) -> None:
        if not message.from_user or message.chat.type != "private":
            log.info(
                "Content ignored: reason=not_private_or_no_user chat_id=%s content_type=%s",
                message.chat.id,
                message.content_type,
            )
            return
        if not await self.access.guard_message(message):
            return

        user_id = message.from_user.id
        event_setup = self.context.state.awaiting_event.get(user_id)
        if event_setup and message.text:
            await self._handle_event_time(message, event_setup)
            return
        if user_id in self.context.state.awaiting_schedule and message.text:
            await self._handle_schedule_time(message)
            return
        if message.media_group_id:
            key = (message.chat.id, message.media_group_id)
            album = self.context.state.albums.setdefault(key, AlbumBuffer())
            album.messages.append(message)
            log.info(
                "Album item buffered: admin_id=%s media_group_id=%s items=%s",
                user_id, message.media_group_id, len(album.messages),
            )
            if album.task:
                album.task.cancel()
            album.task = asyncio.create_task(self._finish_album(key))
            return
        await self._create_draft([message])

    async def _handle_event_time(self, message: Message, setup: EventSetup) -> None:
        log.info(
            "Event time input: admin_id=%s post_id=%s stage=%s",
            message.from_user.id,
            setup.post_id,
            "start" if setup.starts_at is None else "end",
        )
        try:
            value = parse_schedule(message.text, self.context.settings.timezone)
        except ValueError as exc:
            await message.answer(str(exc))
            return
        if setup.starts_at is None:
            setup.starts_at = value
            await message.answer(
                "Теперь введите дату и время окончания мероприятия в формате "
                f"ДД.ММ.ГГГГ ЧЧ:ММ ({self.context.settings.timezone_name})."
            )
            return
        if value <= setup.starts_at:
            await message.answer("Окончание должно быть позже начала мероприятия.")
            return
        if await self.context.db.set_event(setup.post_id, setup.starts_at, value):
            post_id = setup.post_id
            self.context.state.awaiting_event.pop(message.from_user.id, None)
            await message.answer("Регистрация добавлена к публикации.")
            await self.show_draft(message.chat.id, post_id)
        else:
            self.context.state.awaiting_event.pop(message.from_user.id, None)
            await message.answer("Черновик уже закрыт.")

    async def _handle_schedule_time(self, message: Message) -> None:
        post_id = self.context.state.awaiting_schedule[message.from_user.id]
        log.info("Post schedule input: admin_id=%s post_id=%s", message.from_user.id, post_id)
        try:
            when = parse_schedule(message.text, self.context.settings.timezone)
        except ValueError as exc:
            await message.answer(str(exc))
            return
        post = await self.context.db.post(post_id)
        if post and post["event"]:
            starts_at = datetime.fromisoformat(post["event"]["starts_at"])
            if when >= starts_at:
                await message.answer("Публикация должна выйти раньше начала мероприятия.")
                return
        if await self.context.db.schedule(post_id, when):
            self.context.state.awaiting_schedule.pop(message.from_user.id, None)
            await message.answer(
                f"Публикация #{post_id} запланирована на "
                f"{when.astimezone(self.context.settings.timezone):%d.%m.%Y %H:%M} "
                f"({self.context.settings.timezone_name})."
            )
        else:
            await message.answer("Не выбрана ни одна цель или черновик уже закрыт.")

    async def _finish_album(self, key: tuple[int, str]) -> None:
        try:
            await asyncio.sleep(1)
            album = self.context.state.albums.pop(key, None)
            if album:
                album.messages.sort(key=lambda item: item.message_id)
                await self._create_draft(album.messages)
        except asyncio.CancelledError:
            return

    async def _download_photo(self, message: Message) -> str:
        photo = message.photo[-1]
        path = self.context.settings.media_dir / f"{uuid.uuid4().hex}.jpg"
        await self.context.bot.download(photo, destination=path)
        return str(path)

    async def _create_draft(self, messages: list[Message]) -> None:
        lead = next(
            (item for item in messages if item.caption or item.text or item.rich_message),
            messages[0],
        )
        rich_message = rich_message_to_json(lead.rich_message)
        text = rich_message_preview(rich_message) if rich_message else (lead.text or lead.caption or "")
        entities = [] if rich_message else entities_to_json(lead.entities or lead.caption_entities)
        media_paths = [await self._download_photo(item) for item in messages if item.photo]
        post_id = await self.context.db.create_post(
            lead.from_user.id, text, entities, media_paths, rich_message
        )
        log.info(
            "Draft created: post_id=%s admin_id=%s text_len=%s media_count=%s "
            "entities=%s rich_message=%s",
            post_id, lead.from_user.id, len(text), len(media_paths),
            [item.get("type") for item in entities], rich_message is not None,
        )
        await self.show_draft(lead.chat.id, post_id)

    async def show_draft(self, chat_id: int, post_id: int, edit: Message | None = None) -> None:
        post = await self.context.db.post(post_id)
        selected = {item["target_key"] for item in post["deliveries"]}
        text_preview = post["text"][:500] or "[без текста]"
        if post["event"]:
            event_status = (
                "включена\n"
                f"Начало: {format_local(post['event']['starts_at'], self.context.settings.timezone)}\n"
                f"Окончание: {format_local(post['event']['ends_at'], self.context.settings.timezone)}"
            )
        else:
            event_status = "выключена"
        if post["rich_message"]:
            body = (
                f"Настройки поста #{post_id}\n\n"
                "Формат: Rich Message\n"
                f"Регистрация: {event_status}\n"
                "Выберите цели публикации."
            )
        else:
            body = (
                f"Черновик #{post_id}\n\n{text_preview}\n\n"
                f"Изображений: {len(post['media_paths'])}\n"
                "Формат: обычный\n"
                f"Регистрация: {event_status}\n"
                "Выберите цели публикации."
            )
        markup = draft_keyboard(
            post_id, selected, self.context.settings, bool(post["event"])
        )
        if edit:
            await edit.edit_text(body, reply_markup=markup)
        else:
            if post["rich_message"]:
                await self.context.bot.send_rich_message(
                    chat_id, rich_message_from_json(post["rich_message"])
                )
            await self.context.bot.send_message(chat_id, body, reply_markup=markup)

    async def toggle_target(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        _, post_raw, index_raw = callback.data.split(":")
        post_id, index = int(post_raw), int(index_raw)
        post = await self.context.db.post(post_id)
        if not post or post["status"] != "draft":
            await callback.answer("Черновик уже закрыт", show_alert=True)
            return
        target = self.context.settings.targets[index]
        await self.context.db.toggle_delivery(
            post_id, target.key, target.name, target.destination, target.message_thread_id
        )
        await self.show_draft(callback.message.chat.id, post_id, callback.message)
        await callback.answer()

    async def toggle_event(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        post = await self.context.db.post(post_id)
        if not post or post["status"] != "draft":
            await callback.answer("Черновик уже закрыт", show_alert=True)
            return
        if post["event"]:
            await self.context.db.remove_event(post_id)
            self.context.state.awaiting_event.pop(callback.from_user.id, None)
            await self.show_draft(callback.message.chat.id, post_id, callback.message)
            await callback.answer("Регистрация отключена")
            return
        self.context.state.awaiting_schedule.pop(callback.from_user.id, None)
        self.context.state.awaiting_event[callback.from_user.id] = EventSetup(post_id)
        await callback.message.answer(
            "Введите дату и время начала мероприятия в формате "
            f"ДД.ММ.ГГГГ ЧЧ:ММ. Часовой пояс: {self.context.settings.timezone_name}."
        )
        await callback.answer()

    async def publish_now(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        post = await self.context.db.post(post_id)
        if post and post["event"]:
            starts_at = datetime.fromisoformat(post["event"]["starts_at"])
            if starts_at <= datetime.now(timezone.utc):
                await callback.answer("Мероприятие уже началось", show_alert=True)
                return
        if await self.context.db.schedule(post_id, datetime.now(timezone.utc)):
            self.context.state.awaiting_event.pop(callback.from_user.id, None)
            await callback.message.edit_text(f"Публикация #{post_id} поставлена в очередь.")
        else:
            await callback.answer("Выберите хотя бы одну цель", show_alert=True)

    async def ask_schedule(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        post = await self.context.db.post(post_id)
        if not post or not post["deliveries"]:
            await callback.answer("Выберите хотя бы одну цель", show_alert=True)
            return
        self.context.state.awaiting_event.pop(callback.from_user.id, None)
        self.context.state.awaiting_schedule[callback.from_user.id] = post_id
        await callback.message.answer(
            f"Введите дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ. "
            f"Часовой пояс: {self.context.settings.timezone_name}."
        )
        await callback.answer()

    async def cancel(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        self.context.state.awaiting_schedule.pop(callback.from_user.id, None)
        self.context.state.awaiting_event.pop(callback.from_user.id, None)
        post = await self.context.db.post(post_id)
        if await self.context.db.cancel(post_id):
            if post:
                remove_media(post["media_paths"])
            await callback.message.edit_text(f"Публикация #{post_id} отменена.")
        else:
            await callback.answer("Публикацию уже нельзя отменить", show_alert=True)
