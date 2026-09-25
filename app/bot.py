from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, User

from .config import Settings
from .db import Database, Delivery
from .formatting import (
    entities_to_json,
    format_local,
    parse_schedule,
    rich_message_from_json,
    rich_message_preview,
    rich_message_to_json,
)
from .keyboards import (
    admin_event_keyboard,
    attendance_keyboard,
    confirm_event_cancellation_keyboard,
    draft_keyboard,
    event_registration_keyboard,
    past_events_keyboard,
    profile_keyboard,
    queue_cancel_keyboard,
    registration_cancel_keyboard,
    reminder_choice_keyboard,
    user_menu_keyboard,
)
from .logging_middleware import UpdateLoggingMiddleware
from .publishers import TelegramPublisher

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Album:
    messages: list[Message] = field(default_factory=list)
    task: asyncio.Task | None = None


@dataclass(slots=True)
class EventSetup:
    post_id: int
    starts_at: datetime | None = None


class SecretaryBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.bot = Bot(settings.telegram_bot_token)
        self.dp = Dispatcher()
        self.router = Router()
        self.db = Database(settings.database_path)
        self.albums: dict[tuple[int, str], Album] = {}
        self.awaiting_schedule: dict[int, int] = {}
        self.awaiting_event: dict[int, EventSetup] = {}
        self.bot_username: str | None = None
        self.dp.update.outer_middleware(UpdateLoggingMiddleware())
        self._register_handlers()
        self.dp.include_router(self.router)

    def _is_admin(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self.settings.admin_ids

    async def _guard_message(self, message: Message) -> bool:
        if not self._is_admin(message.from_user.id if message.from_user else None):
            log.info(
                "Admin message ignored: reason=not_admin user_id=%s chat_id=%s content_type=%s",
                message.from_user.id if message.from_user else None,
                message.chat.id,
                message.content_type,
            )
            return False
        if message.chat.type != "private":
            log.info(
                "Admin message ignored: reason=not_private user_id=%s chat_id=%s chat_type=%s",
                message.from_user.id if message.from_user else None,
                message.chat.id,
                message.chat.type,
            )
            return False
        return True

    async def _guard_callback(self, callback: CallbackQuery) -> bool:
        if (
            not self._is_admin(callback.from_user.id)
            or not callback.message
            or callback.message.chat.type != "private"
        ):
            log.info(
                "Admin callback rejected: user_id=%s data=%r",
                callback.from_user.id,
                callback.data,
            )
            await callback.answer("Доступ запрещён", show_alert=True)
            return False
        return True

    def _register_handlers(self) -> None:
        self.router.message.register(self.start, CommandStart())
        self.router.message.register(self.help, Command("help"))
        self.router.message.register(self.queue, Command("queue"))
        self.router.message.register(self.my_events, Command("events"))
        self.router.message.register(self.profile, Command("profile"))
        self.router.message.register(self.admin_registrations, Command("registrations"))
        self.router.callback_query.register(self.toggle_target, F.data.startswith("target:"))
        self.router.callback_query.register(self.toggle_event, F.data.startswith("event:"))
        self.router.callback_query.register(self.publish_now, F.data.startswith("now:"))
        self.router.callback_query.register(self.ask_schedule, F.data.startswith("schedule:"))
        self.router.callback_query.register(self.cancel, F.data.startswith("cancel:"))
        self.router.callback_query.register(self.choose_reminder, F.data.startswith("reminder:"))
        self.router.callback_query.register(
            self.show_available_events, F.data == "available_events"
        )
        self.router.callback_query.register(
            self.register_from_menu, F.data.startswith("register_event:")
        )
        self.router.callback_query.register(self.show_my_events, F.data == "my_events")
        self.router.callback_query.register(self.edit_profile, F.data == "edit_profile")
        self.router.callback_query.register(self.unregister, F.data.startswith("unregister:"))
        self.router.callback_query.register(self.record_attendance, F.data.startswith("attendance:"))
        self.router.callback_query.register(self.show_participants, F.data.startswith("participants:"))
        self.router.callback_query.register(self.show_past_events, F.data == "past_events")
        self.router.callback_query.register(
            self.ask_cancel_event, F.data.startswith("cancel_event:")
        )
        self.router.callback_query.register(
            self.confirm_cancel_event, F.data.startswith("confirm_cancel_event:")
        )
        self.router.callback_query.register(
            self.dismiss_cancel_event, F.data == "dismiss_cancel_event"
        )
        self.router.message.register(
            self.content, F.content_type.in_({"text", "photo", "rich_message"})
        )

    async def start(self, message: Message) -> None:
        if not message.from_user or message.chat.type != "private":
            return
        payload = (message.text or "").partition(" ")[2].strip()
        if payload.startswith("event_") and payload[6:].isdigit():
            await self._begin_user_registration(
                message.from_user, message.answer, int(payload[6:])
            )
            return
        if not self._is_admin(message.from_user.id):
            await message.answer(
                "Здесь можно зарегистрироваться на мероприятие и управлять своими регистрациями.",
                reply_markup=user_menu_keyboard(),
            )
            return
        await message.answer(
            "Отправьте текст, фотографию с подписью или альбом. Затем выберите цели и время публикации.\n\n"
            "/queue — запланированные публикации\n"
            "/registrations — мероприятия и участники\n"
            "/events — мои личные регистрации\n"
            "/profile — изменить имя и фамилию\n"
            "/help — помощь"
        )

    async def help(self, message: Message) -> None:
        if not await self._guard_message(message):
            return
        await message.answer(
            "Поддерживаются текст, ссылки, изображения и Rich Messages. "
            "Оформление Telegram сохраняется. "
            "К публикации можно добавить регистрацию на мероприятие. "
            "Время вводится в формате ДД.ММ.ГГГГ ЧЧ:ММ "
            f"({self.settings.timezone_name})."
        )

    async def queue(self, message: Message) -> None:
        if not await self._guard_message(message):
            return
        rows = await self.db.queue()
        if not rows:
            await message.answer("Очередь пуста.")
            return
        for row in rows:
            await message.answer(
                f"Публикация #{row['id']}\n"
                f"Время: {format_local(row['scheduled_at'], self.settings.timezone)} ({self.settings.timezone_name})\n"
                f"Цели: {row['targets']}",
                reply_markup=queue_cancel_keyboard(row["id"]),
            )

    async def my_events(self, message: Message) -> None:
        if not message.from_user or message.chat.type != "private":
            return
        await self._send_user_events(message.from_user.id, message.answer)

    async def show_my_events(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        await self._send_user_events(callback.from_user.id, callback.message.answer)
        await callback.answer()

    async def show_available_events(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        rows = await self.db.available_events(callback.from_user.id)
        if not rows:
            await callback.message.answer(
                "Сейчас нет доступных мероприятий, на которые вы ещё не зарегистрированы."
            )
        else:
            await callback.message.answer("Доступные мероприятия:")
            for row in rows[:30]:
                await callback.message.answer(
                    f"{self._post_title(row['text'])}\n"
                    f"Начало: {format_local(row['starts_at'], self.settings.timezone)} "
                    f"({self.settings.timezone_name})",
                    reply_markup=event_registration_keyboard(row["post_id"]),
                )
        await callback.answer()

    async def register_from_menu(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        post_id = int(callback.data.split(":")[1])
        await self._begin_user_registration(
            callback.from_user, callback.message.answer, post_id
        )
        await callback.answer()

    async def profile(self, message: Message) -> None:
        if not message.from_user or message.chat.type != "private":
            return
        await self.db.update_telegram_identity(
            message.from_user.id, *self._telegram_identity_values(message.from_user)
        )
        profile = await self.db.profile(message.from_user.id)
        if not profile:
            await message.answer(
                "Профиль появится после вашей первой регистрации на мероприятие."
            )
            return
        await message.answer(
            f"Ваши данные: {profile['full_name']}",
            reply_markup=profile_keyboard(),
        )

    async def edit_profile(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        profile = await self.db.profile(callback.from_user.id)
        if not profile:
            await callback.answer(
                "Профиль появится после первой регистрации", show_alert=True
            )
            return
        if await self.db.registration_flow(callback.from_user.id):
            await callback.answer(
                "Сначала завершите текущую регистрацию", show_alert=True
            )
            return
        await self.db.begin_profile_edit(callback.from_user.id)
        await callback.message.answer(
            f"Сейчас указано: {profile['full_name']}.\n"
            "Введите новое имя и фамилию одним сообщением."
        )
        await callback.answer()

    async def _send_user_events(self, user_id: int, send) -> None:
        rows = await self.db.user_registrations(user_id)
        if not rows:
            await send("У вас пока нет активных регистраций.")
            return
        for row in rows:
            title = self._post_title(row["text"])
            starts = format_local(row["starts_at"], self.settings.timezone)
            reminder = "включено" if row["reminders_enabled"] else "выключено"
            await send(
                f"{title}\nНачало: {starts} ({self.settings.timezone_name})\n"
                f"Напоминание: {reminder}",
                reply_markup=registration_cancel_keyboard(row["post_id"]),
            )

    async def admin_registrations(self, message: Message) -> None:
        if not await self._guard_message(message):
            return
        rows = await self.db.admin_events()
        if not rows:
            await message.answer(
                "Активных мероприятий пока нет.",
                reply_markup=past_events_keyboard(),
            )
            return
        for row in rows[:30]:
            await message.answer(
                f"Мероприятие #{row['post_id']}: {self._post_title(row['text'])}\n"
                f"Начало: {format_local(row['starts_at'], self.settings.timezone)}\n"
                f"Зарегистрировано: {row['registrations']}",
                reply_markup=admin_event_keyboard(row["post_id"]),
            )
        await message.answer(
            "Архив мероприятий:", reply_markup=past_events_keyboard()
        )

    async def show_past_events(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        rows = await self.db.admin_events(past=True)
        if not rows:
            await callback.message.answer("Прошедших мероприятий пока нет.")
        else:
            for row in rows[:30]:
                await callback.message.answer(
                    f"Прошедшее мероприятие #{row['post_id']}: "
                    f"{self._post_title(row['text'])}\n"
                    f"Начало: {format_local(row['starts_at'], self.settings.timezone)}\n"
                    f"Зарегистрировано: {row['registrations']}",
                    reply_markup=admin_event_keyboard(
                        row["post_id"], can_cancel=False
                    ),
                )
        await callback.answer()

    async def show_participants(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        rows = await self.db.event_registrations(post_id)
        if not rows:
            await callback.message.answer("На это мероприятие пока никто не зарегистрирован.")
        else:
            lines = [f"Участники мероприятия #{post_id}:"]
            for index, row in enumerate(rows, 1):
                attendance = " — отменил(а) регистрацию" if row["status"] == "cancelled" else ""
                if row["status"] == "registered" and row["attended"] is not None:
                    attendance = " — был(а)" if row["attended"] else " — не был(а)"
                reminder = " 🔔" if row["reminders_enabled"] else ""
                telegram_name = self._telegram_profile_label(row)
                lines.append(
                    f"{index}. {row['full_name']}\n"
                    f"   Telegram: {telegram_name} · ID {row['user_id']}"
                    f"{reminder}{attendance}"
                )
            for offset in range(0, len(lines), 40):
                await callback.message.answer("\n".join(lines[offset:offset + 40]))
        await callback.answer()

    async def ask_cancel_event(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        await callback.message.answer(
            f"Отменить мероприятие #{post_id}? Зарегистрированные участники получат уведомление.",
            reply_markup=confirm_event_cancellation_keyboard(post_id),
        )
        await callback.answer()

    async def dismiss_cancel_event(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        await callback.message.edit_text("Отмена мероприятия не выполнена.")
        await callback.answer()

    async def confirm_cancel_event(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        participants = await self.db.cancel_event(post_id)
        if participants is None:
            await callback.answer(
                "Мероприятие уже отменено или завершилось", show_alert=True
            )
            return
        title = self._post_title(participants[0]["text"]) if participants else f"#{post_id}"
        notified = 0
        for participant in participants:
            try:
                await self.bot.send_message(
                    participant["user_id"],
                    f"Мероприятие «{title}» отменено организаторами.",
                )
                notified += 1
            except Exception:
                log.exception(
                    "Could not notify user %s about cancelled event %s",
                    participant["user_id"], post_id,
                )
        await callback.message.edit_text(
            f"Мероприятие #{post_id} отменено. Уведомлено участников: "
            f"{notified} из {len(participants)}."
        )
        await callback.answer()

    async def content(self, message: Message) -> None:
        if not message.from_user or message.chat.type != "private":
            log.info(
                "Content ignored: reason=not_private_or_no_user chat_id=%s content_type=%s",
                message.chat.id,
                message.content_type,
            )
            return
        flow = await self.db.registration_flow(message.from_user.id)
        if flow and message.text:
            log.info(
                "Registration form input: user_id=%s post_id=%s stage=%s",
                message.from_user.id,
                flow["post_id"],
                flow["stage"],
            )
            await self._continue_profile(message, flow)
            return
        profile_flow = await self.db.profile_edit_flow(message.from_user.id)
        if profile_flow and message.text:
            log.info(
                "Profile edit input: user_id=%s stage=%s",
                message.from_user.id,
                profile_flow["stage"],
            )
            await self._continue_profile_edit(message, profile_flow)
            return
        if not await self._guard_message(message):
            return
        event_setup = self.awaiting_event.get(message.from_user.id)
        if event_setup and message.text:
            log.info(
                "Event time input: admin_id=%s post_id=%s stage=%s",
                message.from_user.id,
                event_setup.post_id,
                "start" if event_setup.starts_at is None else "end",
            )
            try:
                value = parse_schedule(message.text, self.settings.timezone)
            except ValueError as exc:
                await message.answer(str(exc))
                return
            if event_setup.starts_at is None:
                event_setup.starts_at = value
                await message.answer(
                    "Теперь введите дату и время окончания мероприятия в формате "
                    f"ДД.ММ.ГГГГ ЧЧ:ММ ({self.settings.timezone_name})."
                )
                return
            if value <= event_setup.starts_at:
                await message.answer("Окончание должно быть позже начала мероприятия.")
                return
            if await self.db.set_event(event_setup.post_id, event_setup.starts_at, value):
                post_id = event_setup.post_id
                self.awaiting_event.pop(message.from_user.id, None)
                await message.answer("Регистрация добавлена к публикации.")
                await self._show_draft(message.chat.id, post_id)
            else:
                self.awaiting_event.pop(message.from_user.id, None)
                await message.answer("Черновик уже закрыт.")
            return
        if message.from_user.id in self.awaiting_schedule and message.text:
            post_id = self.awaiting_schedule[message.from_user.id]
            log.info(
                "Post schedule input: admin_id=%s post_id=%s",
                message.from_user.id,
                post_id,
            )
            try:
                when = parse_schedule(message.text, self.settings.timezone)
            except ValueError as exc:
                await message.answer(str(exc))
                return
            post = await self.db.post(post_id)
            if post and post["event"]:
                starts_at = datetime.fromisoformat(post["event"]["starts_at"])
                if when >= starts_at:
                    await message.answer(
                        "Публикация должна выйти раньше начала мероприятия."
                    )
                    return
            if await self.db.schedule(post_id, when):
                self.awaiting_schedule.pop(message.from_user.id, None)
                await message.answer(
                    f"Публикация #{post_id} запланирована на "
                    f"{when.astimezone(self.settings.timezone):%d.%m.%Y %H:%M} ({self.settings.timezone_name})."
                )
            else:
                await message.answer("Не выбрана ни одна цель или черновик уже закрыт.")
            return
        if message.media_group_id:
            key = (message.chat.id, message.media_group_id)
            album = self.albums.setdefault(key, Album())
            album.messages.append(message)
            log.info(
                "Album item buffered: admin_id=%s media_group_id=%s items=%s",
                message.from_user.id,
                message.media_group_id,
                len(album.messages),
            )
            if album.task:
                album.task.cancel()
            album.task = asyncio.create_task(self._finish_album(key))
            return
        await self._create_draft([message])

    async def _finish_album(self, key: tuple[int, str]) -> None:
        try:
            await asyncio.sleep(1)
            album = self.albums.pop(key, None)
            if album:
                album.messages.sort(key=lambda item: item.message_id)
                await self._create_draft(album.messages)
        except asyncio.CancelledError:
            return

    async def _download_photo(self, message: Message) -> str:
        photo = message.photo[-1]
        suffix = ".jpg"
        path = self.settings.media_dir / f"{uuid.uuid4().hex}{suffix}"
        await self.bot.download(photo, destination=path)
        return str(path)

    async def _create_draft(self, messages: list[Message]) -> None:
        lead = next(
            (
                item for item in messages
                if item.caption or item.text or item.rich_message
            ),
            messages[0],
        )
        rich_message = rich_message_to_json(lead.rich_message)
        text = (
            rich_message_preview(rich_message)
            if rich_message else (lead.text or lead.caption or "")
        )
        entities = [] if rich_message else entities_to_json(
            lead.entities or lead.caption_entities
        )
        media_paths = [await self._download_photo(item) for item in messages if item.photo]
        post_id = await self.db.create_post(
            lead.from_user.id, text, entities, media_paths, rich_message
        )
        log.info(
            "Draft created: post_id=%s admin_id=%s text_len=%s media_count=%s "
            "entities=%s rich_message=%s",
            post_id,
            lead.from_user.id,
            len(text),
            len(media_paths),
            [item.get("type") for item in entities],
            rich_message is not None,
        )
        await self._show_draft(lead.chat.id, post_id)

    async def _show_draft(self, chat_id: int, post_id: int, edit: Message | None = None) -> None:
        post = await self.db.post(post_id)
        selected = {item["target_key"] for item in post["deliveries"]}
        text_preview = post["text"][:500] or "[без текста]"
        if post["event"]:
            event_status = (
                "включена\n"
                f"Начало: {format_local(post['event']['starts_at'], self.settings.timezone)}\n"
                f"Окончание: {format_local(post['event']['ends_at'], self.settings.timezone)}"
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
        markup = draft_keyboard(post_id, selected, self.settings, bool(post["event"]))
        if edit:
            await edit.edit_text(body, reply_markup=markup)
        else:
            if post["rich_message"]:
                await self.bot.send_rich_message(
                    chat_id,
                    rich_message_from_json(post["rich_message"]),
                )
            await self.bot.send_message(chat_id, body, reply_markup=markup)

    async def toggle_target(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        _, post_raw, index_raw = callback.data.split(":")
        post_id, index = int(post_raw), int(index_raw)
        post = await self.db.post(post_id)
        if not post or post["status"] != "draft":
            await callback.answer("Черновик уже закрыт", show_alert=True)
            return
        target = self.settings.targets[index]
        await self.db.toggle_delivery(
            post_id,
            target.key,
            target.name,
            target.destination,
            target.message_thread_id,
        )
        await self._show_draft(callback.message.chat.id, post_id, callback.message)
        await callback.answer()

    async def toggle_event(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        post = await self.db.post(post_id)
        if not post or post["status"] != "draft":
            await callback.answer("Черновик уже закрыт", show_alert=True)
            return
        if post["event"]:
            await self.db.remove_event(post_id)
            self.awaiting_event.pop(callback.from_user.id, None)
            await self._show_draft(callback.message.chat.id, post_id, callback.message)
            await callback.answer("Регистрация отключена")
            return
        self.awaiting_schedule.pop(callback.from_user.id, None)
        self.awaiting_event[callback.from_user.id] = EventSetup(post_id)
        await callback.message.answer(
            "Введите дату и время начала мероприятия в формате "
            f"ДД.ММ.ГГГГ ЧЧ:ММ. Часовой пояс: {self.settings.timezone_name}."
        )
        await callback.answer()

    async def _begin_user_registration(self, user: User, send, post_id: int) -> None:
        user_id = user.id
        if await self.db.profile_edit_flow(user_id):
            await send(
                "Сначала завершите изменение фамилии и имени, затем снова нажмите «Зарегистрироваться»."
            )
            return
        event = await self.db.event_for_registration(post_id)
        if not event:
            await send("Регистрация на это мероприятие недоступна.")
            return
        current = await self.db.registration(user_id, post_id)
        if current and current["status"] == "registered":
            await send(
                f"Вы уже зарегистрированы: {self._post_title(event['text'])}.",
                reply_markup=registration_cancel_keyboard(post_id),
            )
            return
        profile = await self.db.profile(user_id)
        if profile:
            await self.db.update_telegram_identity(
                user_id, *self._telegram_identity_values(user)
            )
            await self.db.begin_registration_flow(user_id, post_id, "reminder")
            await send(
                f"Вы регистрируетесь на мероприятие: {self._post_title(event['text'])}.\n"
                f"{self._reminder_question()}",
                reply_markup=reminder_choice_keyboard(post_id),
            )
            return
        await self.db.begin_registration_flow(user_id, post_id, "full_name")
        await send(
            "Вы регистрируетесь впервые. Эти данные увидят только администраторы.\n\n"
            "Укажите имя и фамилию одним сообщением."
        )

    async def _continue_profile(self, message: Message, flow: dict) -> None:
        value = " ".join((message.text or "").strip().split())
        if not 1 < len(value) <= 160:
            await message.answer("Введите имя и фамилию длиной от 2 до 160 символов.")
            return
        if flow["stage"] == "full_name":
            await self.db.save_profile(
                message.from_user.id,
                value,
                *self._telegram_identity_values(message.from_user),
            )
            await self.db.update_registration_flow(message.from_user.id, "reminder")
            await message.answer(
                self._reminder_question(),
                reply_markup=reminder_choice_keyboard(flow["post_id"]),
            )

    async def _continue_profile_edit(self, message: Message, flow: dict) -> None:
        value = " ".join((message.text or "").strip().split())
        if not 1 < len(value) <= 160:
            await message.answer("Введите имя и фамилию длиной от 2 до 160 символов.")
            return
        if flow["stage"] == "full_name":
            await self.db.save_profile(
                message.from_user.id,
                value,
                *self._telegram_identity_values(message.from_user),
            )
            await self.db.delete_profile_edit(message.from_user.id)
            await message.answer(
                f"Данные обновлены: {value}.",
                reply_markup=user_menu_keyboard(),
            )

    async def choose_reminder(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        _, post_raw, enabled_raw = callback.data.split(":")
        post_id = int(post_raw)
        flow = await self.db.registration_flow(callback.from_user.id)
        if not flow or flow["post_id"] != post_id or flow["stage"] != "reminder":
            await callback.answer("Регистрация уже завершена или устарела", show_alert=True)
            return
        registered = await self.db.register(
            callback.from_user.id, post_id, enabled_raw == "1"
        )
        await self.db.delete_registration_flow(callback.from_user.id)
        if not registered:
            await callback.message.edit_text("Регистрация на это мероприятие уже закрыта.")
        else:
            await callback.message.edit_text(
                "Вы зарегистрированы. Мероприятие появилось в разделе «Мои мероприятия».",
                reply_markup=registration_cancel_keyboard(post_id),
            )
        await callback.answer()

    async def unregister(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        post_id = int(callback.data.split(":")[1])
        if await self.db.cancel_registration(callback.from_user.id, post_id):
            await callback.message.edit_text("Регистрация отменена.")
            await callback.answer()
        else:
            await callback.answer(
                "Регистрация уже отменена или мероприятие началось", show_alert=True
            )

    async def record_attendance(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        _, post_raw, attended_raw = callback.data.split(":")
        if await self.db.record_attendance(
            callback.from_user.id, int(post_raw), attended_raw == "1"
        ):
            answer = "Спасибо! Посещение отмечено."
            await callback.message.edit_text(answer)
            await callback.answer()
        else:
            await callback.answer("Ответ уже неактуален", show_alert=True)

    async def publish_now(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        post = await self.db.post(post_id)
        if post and post["event"]:
            starts_at = datetime.fromisoformat(post["event"]["starts_at"])
            if starts_at <= datetime.now(timezone.utc):
                await callback.answer("Мероприятие уже началось", show_alert=True)
                return
        if await self.db.schedule(post_id, datetime.now(timezone.utc)):
            self.awaiting_event.pop(callback.from_user.id, None)
            await callback.message.edit_text(f"Публикация #{post_id} поставлена в очередь.")
        else:
            await callback.answer("Выберите хотя бы одну цель", show_alert=True)

    async def ask_schedule(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        post = await self.db.post(post_id)
        if not post or not post["deliveries"]:
            await callback.answer("Выберите хотя бы одну цель", show_alert=True)
            return
        self.awaiting_event.pop(callback.from_user.id, None)
        self.awaiting_schedule[callback.from_user.id] = post_id
        await callback.message.answer(
            f"Введите дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ. Часовой пояс: {self.settings.timezone_name}."
        )
        await callback.answer()

    async def cancel(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        self.awaiting_schedule.pop(callback.from_user.id, None)
        self.awaiting_event.pop(callback.from_user.id, None)
        post = await self.db.post(post_id)
        if await self.db.cancel(post_id):
            if post:
                self._remove_media(post["media_paths"])
            await callback.message.edit_text(f"Публикация #{post_id} отменена.")
        else:
            await callback.answer("Публикацию уже нельзя отменить", show_alert=True)

    async def scheduler(self) -> None:
        telegram = TelegramPublisher(self.bot)
        while True:
            try:
                delivery = await self.db.claim_due()
                if delivery:
                    log.info(
                        "Delivery claimed: delivery_id=%s post_id=%s target=%s attempt=%s",
                        delivery.id,
                        delivery.post_id,
                        delivery.target_key,
                        delivery.attempts + 1,
                    )
                    try:
                        registration_url = None
                        if delivery.event_enabled and self.bot_username:
                            registration_url = (
                                f"https://t.me/{self.bot_username}?start=event_{delivery.post_id}"
                            )
                        external_id = await telegram.publish(delivery, registration_url)
                        await self.db.delivery_succeeded(delivery.id, external_id)
                        log.info(
                            "Delivery succeeded: delivery_id=%s post_id=%s external_id=%s",
                            delivery.id,
                            delivery.post_id,
                            external_id,
                        )
                        await self._notify_admin(
                            delivery.creator_id,
                            f"✅ Публикация #{delivery.post_id}: «{delivery.target_name}» — опубликовано.",
                        )
                    except Exception as exc:
                        log.exception("Delivery %s failed", delivery.id)
                        permanent = isinstance(exc, (TelegramBadRequest, TelegramForbiddenError))
                        max_attempts = 1 if permanent else self.settings.max_delivery_attempts
                        await self.db.delivery_failed(delivery.id, str(exc), max_attempts)
                        attempt = delivery.attempts + 1
                        reason = self._friendly_delivery_error(exc)
                        if permanent or attempt >= self.settings.max_delivery_attempts:
                            await self._notify_admin(
                                delivery.creator_id,
                                f"❌ Публикация #{delivery.post_id}: «{delivery.target_name}» — не опубликовано.\n"
                                f"Причина: {reason}",
                            )
                        else:
                            await self._notify_admin(
                                delivery.creator_id,
                                f"⚠️ Публикация #{delivery.post_id}: «{delivery.target_name}» — попытка "
                                f"{attempt}/{self.settings.max_delivery_attempts} не удалась. Бот повторит отправку.\n"
                                f"Причина: {reason}",
                            )
                    continue
                reminders = await self.db.due_reminders(
                    self.settings.event_reminder_hours
                )
                if reminders:
                    log.info("Due event reminders found: count=%s", len(reminders))
                for reminder in reminders:
                    try:
                        await self.bot.send_message(
                            reminder["user_id"],
                            f"Напоминание: скоро начнётся мероприятие «{self._post_title(reminder['text'])}».\n"
                            f"Начало: {format_local(reminder['starts_at'], self.settings.timezone)} "
                            f"({self.settings.timezone_name}).",
                            reply_markup=registration_cancel_keyboard(reminder["post_id"]),
                        )
                        await self.db.mark_reminder_sent(
                            reminder["user_id"], reminder["post_id"]
                        )
                        log.info(
                            "Event reminder sent: post_id=%s user_id=%s",
                            reminder["post_id"],
                            reminder["user_id"],
                        )
                    except TelegramForbiddenError:
                        log.warning(
                            "Event reminder skipped: reason=bot_blocked post_id=%s user_id=%s",
                            reminder["post_id"],
                            reminder["user_id"],
                        )
                        await self.db.mark_reminder_sent(
                            reminder["user_id"], reminder["post_id"]
                        )
                    except Exception:
                        log.exception("Could not send event reminder")
                attendance_prompts = await self.db.due_attendance_prompts()
                if attendance_prompts:
                    log.info(
                        "Due attendance prompts found: count=%s",
                        len(attendance_prompts),
                    )
                for attendance in attendance_prompts:
                    try:
                        await self.bot.send_message(
                            attendance["user_id"],
                            f"Вы посетили мероприятие «{self._post_title(attendance['text'])}»?",
                            reply_markup=attendance_keyboard(attendance["post_id"]),
                        )
                        await self.db.mark_attendance_prompt_sent(
                            attendance["user_id"], attendance["post_id"]
                        )
                        log.info(
                            "Attendance prompt sent: post_id=%s user_id=%s",
                            attendance["post_id"],
                            attendance["user_id"],
                        )
                    except TelegramForbiddenError:
                        log.warning(
                            "Attendance prompt skipped: reason=bot_blocked post_id=%s user_id=%s",
                            attendance["post_id"],
                            attendance["user_id"],
                        )
                        await self.db.mark_attendance_prompt_sent(
                            attendance["user_id"], attendance["post_id"]
                        )
                    except Exception:
                        log.exception("Could not send attendance prompt")
                for notice in await self.db.terminal_notifications():
                    lines = [f"Публикация #{notice['id']}: {'завершена' if notice['status'] == 'sent' else 'завершена с ошибками' }."]
                    for item in notice["deliveries"]:
                        icon = "✅" if item["status"] == "sent" else "❌"
                        lines.append(f"{icon} {item['target_name']}" + (f": {item['last_error']}" if item["last_error"] else ""))
                    try:
                        await self.bot.send_message(notice["creator_id"], "\n".join(lines))
                        await self.db.mark_notified(notice["id"])
                        post = await self.db.post(notice["id"])
                        if post:
                            self._remove_media(post["media_paths"])
                    except Exception:
                        log.exception("Could not notify admin")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Scheduler loop failed")
            await asyncio.sleep(self.settings.scheduler_interval_seconds)

    @staticmethod
    def _remove_media(paths: list[str]) -> None:
        for path in paths:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                log.warning("Could not remove media file %s", path, exc_info=True)

    @staticmethod
    def _post_title(text: str) -> str:
        clean = " ".join(text.strip().split())
        return (clean[:77] + "...") if len(clean) > 80 else (clean or "Без названия")

    @staticmethod
    def _telegram_identity_values(user: User) -> tuple[str | None, str | None, str | None]:
        return user.username, user.first_name, user.last_name

    @staticmethod
    def _telegram_profile_label(profile: dict) -> str:
        if profile.get("telegram_username"):
            return f"@{profile['telegram_username']}"
        display_name = " ".join(
            part
            for part in (
                profile.get("telegram_first_name"),
                profile.get("telegram_last_name"),
            )
            if part
        )
        return display_name or "имя профиля не указано"

    def _reminder_question(self) -> str:
        return (
            "Напомнить вам о мероприятии за "
            f"{self.settings.event_reminder_hours} ч. до начала?"
        )

    async def _notify_admin(self, admin_id: int, text: str) -> None:
        try:
            await self.bot.send_message(admin_id, text)
        except Exception:
            log.exception("Could not send delivery status to admin %s", admin_id)

    @staticmethod
    def _friendly_delivery_error(error: Exception) -> str:
        raw = str(error)
        if "TOPIC_CLOSED" in raw:
            return "топик Telegram закрыт. Откройте его или укажите другой message_thread_id."
        if "message thread not found" in raw.lower():
            return "топик Telegram не найден. Проверьте message_thread_id."
        if "chat not found" in raw.lower():
            return "чат Telegram не найден или бот не добавлен в него."
        if isinstance(error, TelegramForbiddenError):
            return "у бота нет права публиковать в этом Telegram-чате."
        return raw[:700]

    async def run(self) -> None:
        log.info("Initializing database: path=%s", self.settings.database_path)
        await self.db.initialize()
        me = await self.bot.get_me()
        self.bot_username = me.username
        log.info(
            "Bot initialized: id=%s username=@%s targets=%s",
            me.id,
            me.username,
            len(self.settings.targets),
        )
        scheduler_task = asyncio.create_task(self.scheduler())
        try:
            await self.dp.start_polling(self.bot, allowed_updates=self.dp.resolve_used_update_types())
        finally:
            scheduler_task.cancel()
            await asyncio.gather(scheduler_task, return_exceptions=True)
            await self.bot.session.close()
