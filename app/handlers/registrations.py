from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, User

from ..access import AdminAccess
from ..formatting import format_local
from ..keyboards import (
    admin_events_page_keyboard,
    available_events_keyboard,
    binary_registration_keyboard,
    confirm_event_cancellation_keyboard,
    profile_answer_keyboard,
    profile_keyboard,
    registration_cancel_keyboard,
    reminder_choice_keyboard,
    user_events_keyboard,
    user_menu_keyboard,
)
from ..presentation import (
    event_title,
    reminder_offset_label,
    telegram_identity_values,
    telegram_profile_label,
)
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
        router.callback_query.register(
            self.admin_registrations_button, F.data == "admin_registrations"
        )
        router.callback_query.register(self.choose_reminder, F.data.startswith("reminder:"))
        router.callback_query.register(
            self.answer_registration_question,
            F.data.startswith("registration_answer:"),
        )
        router.callback_query.register(self.show_available_events, F.data == "available_events")
        router.callback_query.register(
            self.paginate_available_events, F.data.startswith("available_events_page:")
        )
        router.callback_query.register(self.register_from_menu, F.data.startswith("register_event:"))
        router.callback_query.register(self.show_my_events, F.data == "my_events")
        router.callback_query.register(
            self.paginate_my_events, F.data.startswith("my_events_page:")
        )
        router.callback_query.register(self.show_profile, F.data == "profile_settings")
        router.callback_query.register(self.edit_profile, F.data == "edit_profile")
        router.callback_query.register(
            self.answer_profile_question, F.data.startswith("profile_answer:")
        )
        router.callback_query.register(self.unregister, F.data.startswith("unregister:"))
        router.callback_query.register(self.record_attendance, F.data.startswith("attendance:"))
        router.callback_query.register(self.show_participants, F.data.startswith("participants:"))
        router.callback_query.register(self.show_past_events, F.data == "past_events")
        router.callback_query.register(
            self.paginate_admin_events, F.data.startswith("admin_events_page:")
        )
        router.callback_query.register(self.ask_cancel_event, F.data.startswith("cancel_event:"))
        router.callback_query.register(
            self.confirm_cancel_event, F.data.startswith("confirm_cancel_event:")
        )
        router.callback_query.register(self.dismiss_cancel_event, F.data == "dismiss_cancel_event")
        router.callback_query.register(self.noop, F.data == "noop")

    async def my_events(self, message: Message) -> None:
        if not message.from_user or message.chat.type != "private":
            return
        await self._send_user_events_page(message.from_user.id, 0, message.answer)

    async def show_my_events(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        await self._send_user_events_page(
            callback.from_user.id, 0, callback.message.answer
        )
        await callback.answer()

    async def paginate_my_events(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        page = int(callback.data.rsplit(":", 1)[1])
        await self._send_user_events_page(
            callback.from_user.id, page, callback.message.edit_text
        )
        await callback.answer()

    async def show_available_events(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        await self._send_available_events_page(
            callback.from_user.id, 0, callback.message.answer
        )
        await callback.answer()

    async def paginate_available_events(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        page = int(callback.data.rsplit(":", 1)[1])
        await self._send_available_events_page(
            callback.from_user.id, page, callback.message.edit_text
        )
        await callback.answer()

    async def _send_available_events_page(self, user_id: int, page: int, send) -> None:
        result = await self.context.db.available_events_page(user_id, page)
        if not result.items:
            await send(
                "Сейчас нет доступных мероприятий, на которые вы ещё не зарегистрированы.",
                reply_markup=user_menu_keyboard(
                    show_admin_return=self._is_admin(user_id)
                ),
            )
            return
        lines = [
            "🎟 Доступные мероприятия",
            f"Страница {result.page + 1}/{result.pages}",
        ]
        for index, row in enumerate(result.items, 1):
            starts = format_local(row["starts_at"], self.context.settings.timezone)
            lines.append(
                f"\n{index}. {event_title(row)}\n"
                f"   🗓 {starts} ({self.context.settings.timezone_name})"
            )
        await send(
            "\n".join(lines),
            reply_markup=available_events_keyboard(
                result.items,
                result.page,
                result.pages,
                self._is_admin(user_id),
            ),
        )

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
        await self._send_profile(message.from_user.id, message.answer)

    async def show_profile(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        await self.context.db.update_telegram_identity(
            callback.from_user.id, *telegram_identity_values(callback.from_user)
        )
        await self._send_profile(callback.from_user.id, callback.message.answer)
        await callback.answer()

    async def _send_profile(self, user_id: int, send) -> None:
        profile = await self.context.db.profile(user_id)
        if not profile:
            text = "👤 Профиль пока не настроен."
        else:
            citizen = self._yes_no(profile["is_russian_citizen"])
            student = self._yes_no(profile["is_itmo_student"])
            text = (
                f"👤 Ваш профиль\n\n"
                f"Имя и фамилия: {profile['full_name']}\n"
                f"Гражданин РФ: {citizen}\n"
                f"Студент ИТМО: {student}"
            )
        await send(
            text,
            reply_markup=profile_keyboard(self._is_admin(user_id)),
        )

    def _is_admin(self, user_id: int) -> bool:
        return bool(self.access and self.access.is_admin(user_id))

    @staticmethod
    def _yes_no(value: int | None) -> str:
        if value is None:
            return "не указано"
        return "да" if value else "нет"

    async def edit_profile(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        if await self.context.db.registration_flow(callback.from_user.id):
            await callback.answer("Сначала завершите текущую регистрацию", show_alert=True)
            return
        await self.context.db.begin_profile_edit(callback.from_user.id)
        profile = await self.context.db.profile(callback.from_user.id)
        prefix = f"Сейчас указано: {profile['full_name']}.\n" if profile else ""
        await callback.message.answer(
            f"{prefix}Введите имя и фамилию одним сообщением."
        )
        await callback.answer()

    async def _send_user_events_page(self, user_id: int, page: int, send) -> None:
        result = await self.context.db.user_registrations_page(user_id, page)
        if not result.items:
            await send(
                "У вас пока нет активных регистраций.",
                reply_markup=user_menu_keyboard(
                    show_admin_return=self._is_admin(user_id)
                ),
            )
            return
        lines = [
            "📅 Мои мероприятия",
            f"Страница {result.page + 1}/{result.pages}",
        ]
        for index, row in enumerate(result.items, 1):
            starts = format_local(row["starts_at"], self.context.settings.timezone)
            if row["reminders_enabled"]:
                reminder = reminder_offset_label(row["reminder_offset_minutes"])
            else:
                reminder = "выключено"
            lines.append(
                f"\n{index}. {event_title(row)}\n"
                f"   🗓 {starts} ({self.context.settings.timezone_name})\n"
                f"   🔔 Напоминание: {reminder}"
            )
        await send(
            "\n".join(lines),
            reply_markup=user_events_keyboard(
                result.items,
                result.page,
                result.pages,
                self._is_admin(user_id),
            ),
        )

    async def admin_registrations(self, message: Message) -> None:
        if not await self.access.guard_message(message):
            return
        await self._send_admin_events_page(False, 0, message.answer)

    async def admin_registrations_button(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        await self._send_admin_events_page(False, 0, callback.message.answer)
        await callback.answer()

    async def paginate_admin_events(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        _, kind, page_raw = callback.data.split(":")
        await self._send_admin_events_page(
            kind == "past", int(page_raw), callback.message.edit_text
        )
        await callback.answer()

    async def show_past_events(self, callback: CallbackQuery) -> None:
        """Compatibility handler for buttons sent before paginated lists existed."""
        if not await self.access.guard_callback(callback):
            return
        await self._send_admin_events_page(True, 0, callback.message.edit_text)
        await callback.answer()

    async def _send_admin_events_page(self, past: bool, page: int, send) -> None:
        result = await self.context.db.admin_events_page(past, page)
        heading = "Прошедшие мероприятия" if past else "Активные мероприятия"
        lines = [f"{heading} · страница {result.page + 1}/{result.pages}"]
        if not result.items:
            lines.append("\nСписок пуст.")
        for index, row in enumerate(result.items, 1):
            starts = format_local(row["starts_at"], self.context.settings.timezone)
            lines.append(
                f"\n{index}. {event_title(row)}\n"
                f"   {starts}\n"
                f"   Зарегистрировано: {row['registrations']}"
            )
        await send(
            "\n".join(lines),
            reply_markup=admin_events_page_keyboard(
                result.items, result.page, result.pages, past
            ),
        )

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
                citizen = (
                    "да" if row["is_russian_citizen"] == 1 else
                    "нет" if row["is_russian_citizen"] == 0 else "не указано"
                )
                student = (
                    "да" if row["is_itmo_student"] == 1 else
                    "нет" if row["is_itmo_student"] == 0 else "не указано"
                )
                reminder = (
                    reminder_offset_label(row["reminder_offset_minutes"])
                    if row["reminders_enabled"] else "выключено"
                )
                lines.append(
                    f"{index}. {row['full_name']}\n"
                    f"   Telegram: {telegram_profile_label(row)} · ID {row['user_id']}\n"
                    f"   Гражданин РФ: {citizen} · Студент ИТМО: {student}\n"
                    f"   Напоминание: {reminder}{attendance}"
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
        title = event_title(participants[0]) if participants else f"#{post_id}"
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
                "Сначала завершите настройку профиля, затем снова нажмите «Зарегистрироваться»."
            )
            return
        event = await self.context.db.event_for_registration(post_id)
        if not event:
            await send("Регистрация на это мероприятие недоступна.")
            return
        current = await self.context.db.registration(user_id, post_id)
        if current and current["status"] == "registered":
            await send(
                f"Вы уже зарегистрированы: {event_title(event)}.",
                reply_markup=registration_cancel_keyboard(post_id),
            )
            return
        profile = await self.context.db.profile(user_id)
        profile_complete = profile and all(
            profile[field] is not None
            for field in ("is_russian_citizen", "is_itmo_student")
        )
        if profile_complete:
            await self.context.db.update_telegram_identity(
                user_id, *telegram_identity_values(user)
            )
            await self.context.db.begin_registration_flow(user_id, post_id, "reminder")
            options = await self._available_reminder_options(post_id)
            await send(
                f"Вы регистрируетесь на мероприятие: {event_title(event)}.\n\n"
                "Когда вам напомнить о мероприятии?",
                reply_markup=reminder_choice_keyboard(post_id, options),
            )
            return
        if profile:
            await self.context.db.update_telegram_identity(
                user_id, *telegram_identity_values(user)
            )
            await self.context.db.begin_registration_flow(user_id, post_id, "citizenship")
            await send(
                "Чтобы завершить настройку профиля, ответьте на два вопроса.\n\n"
                "Вы являетесь гражданином РФ?",
                reply_markup=binary_registration_keyboard(post_id, "citizenship"),
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
            await self.context.db.update_registration_flow(
                message.from_user.id, "citizenship"
            )
            await message.answer(
                "Вы являетесь гражданином РФ?",
                reply_markup=binary_registration_keyboard(
                    flow["post_id"], "citizenship"
                ),
            )

    async def answer_registration_question(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        _, post_raw, field, value_raw = callback.data.split(":")
        post_id = int(post_raw)
        flow = await self.context.db.registration_flow(callback.from_user.id)
        expected_stage = "citizenship" if field == "citizenship" else "itmo_student"
        if (
            field not in {"citizenship", "itmo_student"}
            or not flow
            or flow["post_id"] != post_id
            or flow["stage"] != expected_stage
        ):
            await callback.answer("Этот вопрос уже неактуален", show_alert=True)
            return
        value = value_raw == "1"
        if field == "citizenship":
            await self.context.db.update_profile_answers(
                callback.from_user.id, is_russian_citizen=value
            )
            await self.context.db.update_registration_flow(
                callback.from_user.id, "itmo_student"
            )
            await callback.message.edit_text(
                "Вы являетесь студентом ИТМО?",
                reply_markup=binary_registration_keyboard(post_id, "itmo_student"),
            )
        else:
            await self.context.db.update_profile_answers(
                callback.from_user.id, is_itmo_student=value
            )
            await self.context.db.update_registration_flow(
                callback.from_user.id, "reminder"
            )
            await self._show_reminder_options(callback.message, post_id)
        await callback.answer()

    async def _show_reminder_options(self, message: Message, post_id: int) -> None:
        options = await self._available_reminder_options(post_id)
        await message.edit_text(
            "Когда вам напомнить о мероприятии?",
            reply_markup=reminder_choice_keyboard(post_id, options),
        )

    async def _available_reminder_options(self, post_id: int) -> tuple[int, ...]:
        event = await self.context.db.event_for_registration(post_id)
        if not event:
            return ()
        starts_at = datetime.fromisoformat(event["starts_at"])
        now = datetime.now(timezone.utc)
        return tuple(
            minutes
            for minutes in self.context.settings.reminder_options_minutes
            if starts_at - timedelta(minutes=minutes) > now
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
            await self.context.db.update_profile_edit(
                message.from_user.id, "citizenship"
            )
            await message.answer(
                "Вы являетесь гражданином РФ?",
                reply_markup=profile_answer_keyboard("citizenship"),
            )

    async def answer_profile_question(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        _, field, value_raw = callback.data.split(":")
        flow = await self.context.db.profile_edit_flow(callback.from_user.id)
        if (
            field not in {"citizenship", "itmo_student"}
            or not flow
            or flow["stage"] != field
        ):
            await callback.answer("Этот вопрос уже неактуален", show_alert=True)
            return
        value = value_raw == "1"
        if field == "citizenship":
            await self.context.db.update_profile_answers(
                callback.from_user.id, is_russian_citizen=value
            )
            await self.context.db.update_profile_edit(
                callback.from_user.id, "itmo_student"
            )
            await callback.message.edit_text(
                "Вы являетесь студентом ИТМО?",
                reply_markup=profile_answer_keyboard("itmo_student"),
            )
        else:
            await self.context.db.update_profile_answers(
                callback.from_user.id, is_itmo_student=value
            )
            await self.context.db.delete_profile_edit(callback.from_user.id)
            await callback.message.edit_text(
                "Профиль сохранён.",
                reply_markup=user_menu_keyboard(
                    show_admin_return=self._is_admin(callback.from_user.id)
                ),
            )
        await callback.answer()

    async def choose_reminder(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        _, post_raw, offset_raw = callback.data.split(":")
        post_id = int(post_raw)
        flow = await self.context.db.registration_flow(callback.from_user.id)
        if not flow or flow["post_id"] != post_id or flow["stage"] != "reminder":
            await callback.answer("Регистрация уже завершена или устарела", show_alert=True)
            return
        offset = int(offset_raw)
        if offset < 0 or (
            offset != 0
            and offset not in self.context.settings.reminder_options_minutes
        ):
            await callback.answer("Некорректный интервал", show_alert=True)
            return
        if offset and offset not in await self._available_reminder_options(post_id):
            await self._show_reminder_options(callback.message, post_id)
            await callback.answer(
                "Это время напоминания уже прошло. Выберите другой вариант.",
                show_alert=True,
            )
            return
        profile = await self.context.db.profile(callback.from_user.id)
        if not profile or any(
            profile[field] is None
            for field in ("is_russian_citizen", "is_itmo_student")
        ):
            await callback.answer("Сначала заполните профиль", show_alert=True)
            return
        registered = await self.context.db.register(
            callback.from_user.id, post_id, offset or None
        )
        if not registered:
            await callback.message.edit_text("Регистрация на это мероприятие уже закрыта.")
        else:
            await self.context.db.delete_registration_flow(callback.from_user.id)
            await callback.message.edit_text(
                "Вы зарегистрированы. Мероприятие появилось в разделе «Мои мероприятия».",
                reply_markup=registration_cancel_keyboard(post_id),
            )
        await callback.answer()

    async def unregister(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        parts = callback.data.split(":")
        post_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else None
        if await self.context.db.cancel_registration(callback.from_user.id, post_id):
            if page is None:
                await callback.message.edit_text("Регистрация отменена.")
            else:
                await self._send_user_events_page(
                    callback.from_user.id, page, callback.message.edit_text
                )
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

    async def noop(self, callback: CallbackQuery) -> None:
        await callback.answer()
