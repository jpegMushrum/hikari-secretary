from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, User

from ..access import AdminAccess
from ..formatting import format_local
from ..keyboards import (
    admin_event_keyboard,
    confirm_event_cancellation_keyboard,
    event_registration_keyboard,
    past_events_keyboard,
    profile_keyboard,
    registration_cancel_keyboard,
    reminder_choice_keyboard,
    user_menu_keyboard,
)
from ..presentation import post_title, telegram_identity_values, telegram_profile_label
from ..runtime import AppContext

log = logging.getLogger(__name__)


class RegistrationHandlers:
    def __init__(self, context: AppContext, access: AdminAccess):
        self.context = context
        self.access = access

    def register(self, router: Router) -> None:
        router.message.register(self.my_events, Command("events"))
        router.message.register(self.profile, Command("profile"))
        router.message.register(self.admin_registrations, Command("registrations"))
        router.callback_query.register(self.choose_reminder, F.data.startswith("reminder:"))
        router.callback_query.register(self.show_available_events, F.data == "available_events")
        router.callback_query.register(self.register_from_menu, F.data.startswith("register_event:"))
        router.callback_query.register(self.show_my_events, F.data == "my_events")
        router.callback_query.register(self.edit_profile, F.data == "edit_profile")
        router.callback_query.register(self.unregister, F.data.startswith("unregister:"))
        router.callback_query.register(self.record_attendance, F.data.startswith("attendance:"))
        router.callback_query.register(self.show_participants, F.data.startswith("participants:"))
        router.callback_query.register(self.show_past_events, F.data == "past_events")
        router.callback_query.register(self.ask_cancel_event, F.data.startswith("cancel_event:"))
        router.callback_query.register(
            self.confirm_cancel_event, F.data.startswith("confirm_cancel_event:")
        )
        router.callback_query.register(self.dismiss_cancel_event, F.data == "dismiss_cancel_event")

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
        rows = await self.context.db.available_events(callback.from_user.id)
        if not rows:
            await callback.message.answer(
                "Сейчас нет доступных мероприятий, на которые вы ещё не зарегистрированы."
            )
        else:
            await callback.message.answer("Доступные мероприятия:")
            for row in rows[:30]:
                await callback.message.answer(
                    f"{post_title(row['text'])}\n"
                    f"Начало: {format_local(row['starts_at'], self.context.settings.timezone)} "
                    f"({self.context.settings.timezone_name})",
                    reply_markup=event_registration_keyboard(row["post_id"]),
                )
        await callback.answer()

    async def register_from_menu(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        post_id = int(callback.data.split(":")[1])
        await self.begin_registration(callback.from_user, callback.message.answer, post_id)
        await callback.answer()

    async def profile(self, message: Message) -> None:
        if not message.from_user or message.chat.type != "private":
            return
        await self.context.db.update_telegram_identity(
            message.from_user.id, *telegram_identity_values(message.from_user)
        )
        profile = await self.context.db.profile(message.from_user.id)
        if not profile:
            await message.answer("Профиль появится после вашей первой регистрации на мероприятие.")
            return
        await message.answer(
            f"Ваши данные: {profile['full_name']}",
            reply_markup=profile_keyboard(),
        )

    async def edit_profile(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        profile = await self.context.db.profile(callback.from_user.id)
        if not profile:
            await callback.answer("Профиль появится после первой регистрации", show_alert=True)
            return
        if await self.context.db.registration_flow(callback.from_user.id):
            await callback.answer("Сначала завершите текущую регистрацию", show_alert=True)
            return
        await self.context.db.begin_profile_edit(callback.from_user.id)
        await callback.message.answer(
            f"Сейчас указано: {profile['full_name']}.\n"
            "Введите новое имя и фамилию одним сообщением."
        )
        await callback.answer()

    async def _send_user_events(self, user_id: int, send) -> None:
        rows = await self.context.db.user_registrations(user_id)
        if not rows:
            await send("У вас пока нет активных регистраций.")
            return
        for row in rows:
            starts = format_local(row["starts_at"], self.context.settings.timezone)
            reminder = "включено" if row["reminders_enabled"] else "выключено"
            await send(
                f"{post_title(row['text'])}\n"
                f"Начало: {starts} ({self.context.settings.timezone_name})\n"
                f"Напоминание: {reminder}",
                reply_markup=registration_cancel_keyboard(row["post_id"]),
            )

    async def admin_registrations(self, message: Message) -> None:
        if not await self.access.guard_message(message):
            return
        rows = await self.context.db.admin_events()
        if not rows:
            await message.answer("Активных мероприятий пока нет.", reply_markup=past_events_keyboard())
            return
        for row in rows[:30]:
            await message.answer(
                f"Мероприятие #{row['post_id']}: {post_title(row['text'])}\n"
                f"Начало: {format_local(row['starts_at'], self.context.settings.timezone)}\n"
                f"Зарегистрировано: {row['registrations']}",
                reply_markup=admin_event_keyboard(row["post_id"]),
            )
        await message.answer("Архив мероприятий:", reply_markup=past_events_keyboard())

    async def show_past_events(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        rows = await self.context.db.admin_events(past=True)
        if not rows:
            await callback.message.answer("Прошедших мероприятий пока нет.")
        else:
            for row in rows[:30]:
                await callback.message.answer(
                    f"Прошедшее мероприятие #{row['post_id']}: {post_title(row['text'])}\n"
                    f"Начало: {format_local(row['starts_at'], self.context.settings.timezone)}\n"
                    f"Зарегистрировано: {row['registrations']}",
                    reply_markup=admin_event_keyboard(row["post_id"], can_cancel=False),
                )
        await callback.answer()

    async def show_participants(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        rows = await self.context.db.event_registrations(post_id)
        if not rows:
            await callback.message.answer("На это мероприятие пока никто не зарегистрирован.")
        else:
            lines = [f"Участники мероприятия #{post_id}:"]
            for index, row in enumerate(rows, 1):
                attendance = " — отменил(а) регистрацию" if row["status"] == "cancelled" else ""
                if row["status"] == "registered" and row["attended"] is not None:
                    attendance = " — был(а)" if row["attended"] else " — не был(а)"
                reminder = " 🔔" if row["reminders_enabled"] else ""
                lines.append(
                    f"{index}. {row['full_name']}\n"
                    f"   Telegram: {telegram_profile_label(row)} · ID {row['user_id']}"
                    f"{reminder}{attendance}"
                )
            for offset in range(0, len(lines), 40):
                await callback.message.answer("\n".join(lines[offset:offset + 40]))
        await callback.answer()

    async def ask_cancel_event(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        await callback.message.answer(
            f"Отменить мероприятие #{post_id}? Зарегистрированные участники получат уведомление.",
            reply_markup=confirm_event_cancellation_keyboard(post_id),
        )
        await callback.answer()

    async def dismiss_cancel_event(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        await callback.message.edit_text("Отмена мероприятия не выполнена.")
        await callback.answer()

    async def confirm_cancel_event(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        participants = await self.context.db.cancel_event(post_id)
        if participants is None:
            await callback.answer("Мероприятие уже отменено или завершилось", show_alert=True)
            return
        title = post_title(participants[0]["text"]) if participants else f"#{post_id}"
        notified = 0
        for participant in participants:
            try:
                await self.context.bot.send_message(
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

    async def handle_text_flow(self, message: Message) -> bool:
        if not message.from_user or message.chat.type != "private" or not message.text:
            return False
        flow = await self.context.db.registration_flow(message.from_user.id)
        if flow:
            log.info(
                "Registration form input: user_id=%s post_id=%s stage=%s",
                message.from_user.id, flow["post_id"], flow["stage"],
            )
            await self._continue_profile(message, flow)
            return True
        profile_flow = await self.context.db.profile_edit_flow(message.from_user.id)
        if profile_flow:
            log.info(
                "Profile edit input: user_id=%s stage=%s",
                message.from_user.id, profile_flow["stage"],
            )
            await self._continue_profile_edit(message, profile_flow)
            return True
        return False

    async def begin_registration(self, user: User, send, post_id: int) -> None:
        user_id = user.id
        if await self.context.db.profile_edit_flow(user_id):
            await send(
                "Сначала завершите изменение имени и фамилии, затем снова нажмите «Зарегистрироваться»."
            )
            return
        event = await self.context.db.event_for_registration(post_id)
        if not event:
            await send("Регистрация на это мероприятие недоступна.")
            return
        current = await self.context.db.registration(user_id, post_id)
        if current and current["status"] == "registered":
            await send(
                f"Вы уже зарегистрированы: {post_title(event['text'])}.",
                reply_markup=registration_cancel_keyboard(post_id),
            )
            return
        profile = await self.context.db.profile(user_id)
        if profile:
            await self.context.db.update_telegram_identity(
                user_id, *telegram_identity_values(user)
            )
            await self.context.db.begin_registration_flow(user_id, post_id, "reminder")
            await send(
                f"Вы регистрируетесь на мероприятие: {post_title(event['text'])}.\n"
                f"{self.reminder_question()}",
                reply_markup=reminder_choice_keyboard(post_id),
            )
            return
        await self.context.db.begin_registration_flow(user_id, post_id, "full_name")
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
            await self.context.db.save_profile(
                message.from_user.id, value, *telegram_identity_values(message.from_user)
            )
            await self.context.db.update_registration_flow(message.from_user.id, "reminder")
            await message.answer(
                self.reminder_question(),
                reply_markup=reminder_choice_keyboard(flow["post_id"]),
            )

    async def _continue_profile_edit(self, message: Message, flow: dict) -> None:
        value = " ".join((message.text or "").strip().split())
        if not 1 < len(value) <= 160:
            await message.answer("Введите имя и фамилию длиной от 2 до 160 символов.")
            return
        if flow["stage"] == "full_name":
            await self.context.db.save_profile(
                message.from_user.id, value, *telegram_identity_values(message.from_user)
            )
            await self.context.db.delete_profile_edit(message.from_user.id)
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
        flow = await self.context.db.registration_flow(callback.from_user.id)
        if not flow or flow["post_id"] != post_id or flow["stage"] != "reminder":
            await callback.answer("Регистрация уже завершена или устарела", show_alert=True)
            return
        registered = await self.context.db.register(
            callback.from_user.id, post_id, enabled_raw == "1"
        )
        await self.context.db.delete_registration_flow(callback.from_user.id)
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
        if await self.context.db.cancel_registration(callback.from_user.id, post_id):
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
        if await self.context.db.record_attendance(
            callback.from_user.id, int(post_raw), attended_raw == "1"
        ):
            await callback.message.edit_text("Спасибо! Посещение отмечено.")
            await callback.answer()
        else:
            await callback.answer("Ответ уже неактуален", show_alert=True)

    def reminder_question(self) -> str:
        return (
            "Напомнить вам о мероприятии за "
            f"{self.context.settings.event_reminder_hours} ч. до начала?"
        )
