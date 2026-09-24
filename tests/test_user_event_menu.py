import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from app.bot import SecretaryBot
from app.keyboards import user_menu_keyboard


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

    def test_available_events_are_shown_with_registration_buttons(self):
        secretary = object.__new__(SecretaryBot)
        secretary.settings = SimpleNamespace(
            timezone=ZoneInfo("Europe/Moscow"),
            timezone_name="Europe/Moscow",
        )
        secretary.db = SimpleNamespace(
            available_events=AsyncMock(return_value=[{
                "post_id": 7,
                "text": "Японский разговорный клуб",
                "starts_at": "2026-09-26T13:30:00+00:00",
                "ends_at": "2026-09-26T15:30:00+00:00",
            }])
        )
        callback = self._callback()

        asyncio.run(secretary.show_available_events(callback))

        self.assertEqual(callback.message.answer.await_count, 2)
        event_call = callback.message.answer.await_args_list[1]
        self.assertIn("Японский разговорный клуб", event_call.args[0])
        button = event_call.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.callback_data, "register_event:7")
        callback.answer.assert_awaited_once()

    def test_registration_from_menu_uses_existing_flow(self):
        secretary = object.__new__(SecretaryBot)
        secretary._begin_user_registration = AsyncMock()
        callback = self._callback(user_id=201)
        callback.data = "register_event:9"

        asyncio.run(secretary.register_from_menu(callback))

        secretary._begin_user_registration.assert_awaited_once_with(
            201, callback.message.answer, 9
        )
        callback.answer.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
