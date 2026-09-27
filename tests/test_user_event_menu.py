import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from app.handlers.registrations import RegistrationHandlers
from app.keyboards import user_menu_keyboard
from app.db import Page


class UserEventMenuTests(unittest.TestCase):
    @staticmethod
    def _callback(user_id: int = 200):
        message = SimpleNamespace(
            chat=SimpleNamespace(type="private"),
            answer=AsyncMock(),
        )
        return SimpleNamespace(
            from_user=SimpleNamespace(id=user_id),
            message=message,
            data="available_events",
            answer=AsyncMock(),
        )

    def test_user_menu_contains_event_registration_button(self):
        markup = user_menu_keyboard()
        button = markup.inline_keyboard[0][0]
        self.assertEqual(button.text, "Записаться на мероприятие")
        self.assertEqual(button.callback_data, "available_events")
        profile_button = markup.inline_keyboard[2][0]
        self.assertEqual(profile_button.text, "Настройка профиля")
        self.assertEqual(profile_button.callback_data, "profile_settings")

    def test_available_events_are_shown_with_registration_buttons(self):
        context = SimpleNamespace(
            settings=SimpleNamespace(
                timezone=ZoneInfo("Europe/Moscow"),
                timezone_name="Europe/Moscow",
            ),
            db=SimpleNamespace(
                available_events_page=AsyncMock(return_value=Page([{
                    "post_id": 7,
                    "title": "Японский разговорный клуб",
                    "text": "Японский разговорный клуб",
                    "starts_at": "2026-09-26T13:30:00+00:00",
                    "ends_at": "2026-09-26T15:30:00+00:00",
                }], 0, 5, 1)),
            ),
        )
        handlers = RegistrationHandlers(context, None)
        callback = self._callback()

        asyncio.run(handlers.show_available_events(callback))

        self.assertEqual(callback.message.answer.await_count, 1)
        event_call = callback.message.answer.await_args
        self.assertIn("Японский разговорный клуб", event_call.args[0])
        button = event_call.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.callback_data, "register_event:7")
        callback.answer.assert_awaited_once()

    def test_registration_from_menu_uses_existing_flow(self):
        handlers = object.__new__(RegistrationHandlers)
        handlers.begin_registration = AsyncMock()
        callback = self._callback(user_id=201)
        callback.data = "register_event:9"

        asyncio.run(handlers.register_from_menu(callback))

        handlers.begin_registration.assert_awaited_once_with(
            callback.from_user, callback.message.answer, 9
        )
        callback.answer.assert_awaited_once()

    def test_complete_profile_goes_directly_to_reminder_choice(self):
        starts_at = datetime.now(timezone.utc) + timedelta(hours=4)
        db = SimpleNamespace(
            profile_edit_flow=AsyncMock(return_value=None),
            event_for_registration=AsyncMock(return_value={
                "post_id": 9,
                "title": "Клуб",
                "text": "Пост",
                "starts_at": starts_at.isoformat(),
            }),
            registration=AsyncMock(return_value=None),
            profile=AsyncMock(return_value={
                "full_name": "Иван Иванов",
                "is_russian_citizen": 1,
                "is_itmo_student": 1,
            }),
            update_telegram_identity=AsyncMock(),
            begin_registration_flow=AsyncMock(),
        )
        context = SimpleNamespace(
            db=db,
            settings=SimpleNamespace(reminder_options_minutes=(60, 120)),
        )
        handlers = RegistrationHandlers(context, None)
        user = SimpleNamespace(
            id=201, username="ivan", first_name="Иван", last_name="Иванов"
        )
        send = AsyncMock()

        asyncio.run(handlers.begin_registration(user, send, 9))

        db.begin_registration_flow.assert_awaited_once_with(201, 9, "reminder")
        text = send.await_args.args[0]
        self.assertIn("Когда вам напомнить", text)
        callbacks = [
            row[0].callback_data
            for row in send.await_args.kwargs["reply_markup"].inline_keyboard
        ]
        self.assertEqual(callbacks, ["reminder:9:60", "reminder:9:120", "reminder:9:0"])

    def test_citizenship_answer_is_saved_to_profile(self):
        db = SimpleNamespace(
            registration_flow=AsyncMock(return_value={
                "post_id": 7,
                "stage": "citizenship",
            }),
            update_registration_flow=AsyncMock(),
            update_profile_answers=AsyncMock(),
        )
        handlers = RegistrationHandlers(SimpleNamespace(db=db), None)
        callback = self._callback(user_id=201)
        callback.data = "registration_answer:7:citizenship:1"
        callback.message.edit_text = AsyncMock()

        asyncio.run(handlers.answer_registration_question(callback))

        db.update_profile_answers.assert_awaited_once_with(
            201, is_russian_citizen=True
        )
        db.update_registration_flow.assert_awaited_once_with(201, "itmo_student")
        self.assertIn(
            "студентом ИТМО", callback.message.edit_text.await_args.args[0]
        )

    def test_profile_answers_are_saved_without_an_event(self):
        db = SimpleNamespace(
            profile_edit_flow=AsyncMock(return_value={"stage": "citizenship"}),
            update_profile_answers=AsyncMock(),
            update_profile_edit=AsyncMock(),
        )
        handlers = RegistrationHandlers(SimpleNamespace(db=db), None)
        callback = self._callback(user_id=201)
        callback.data = "profile_answer:citizenship:0"
        callback.message.edit_text = AsyncMock()

        asyncio.run(handlers.answer_profile_question(callback))

        db.update_profile_answers.assert_awaited_once_with(
            201, is_russian_citizen=False
        )
        db.update_profile_edit.assert_awaited_once_with(201, "itmo_student")
        self.assertIn(
            "студентом ИТМО", callback.message.edit_text.await_args.args[0]
        )

    def test_reminder_choice_completes_registration_with_questionnaire(self):
        starts_at = datetime.now(timezone.utc) + timedelta(hours=4)
        flow = {
            "post_id": 7,
            "stage": "reminder",
        }
        db = SimpleNamespace(
            registration_flow=AsyncMock(return_value=flow),
            event_for_registration=AsyncMock(return_value={
                "post_id": 7,
                "title": "Клуб",
                "text": "Пост",
                "starts_at": starts_at.isoformat(),
            }),
            profile=AsyncMock(return_value={
                "is_russian_citizen": 1,
                "is_itmo_student": 0,
            }),
            register=AsyncMock(return_value=True),
            delete_registration_flow=AsyncMock(),
        )
        context = SimpleNamespace(
            db=db,
            settings=SimpleNamespace(reminder_options_minutes=(60, 120)),
        )
        handlers = RegistrationHandlers(context, None)
        callback = self._callback(user_id=201)
        callback.data = "reminder:7:120"
        callback.message.edit_text = AsyncMock()

        asyncio.run(handlers.choose_reminder(callback))

        db.register.assert_awaited_once_with(201, 7, 120)
        db.delete_registration_flow.assert_awaited_once_with(201)
        self.assertIn("Вы зарегистрированы", callback.message.edit_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
