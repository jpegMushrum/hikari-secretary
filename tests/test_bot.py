import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.access import AdminAccess
from app.handlers.registrations import RegistrationHandlers
from app.presentation import reminder_offset_label, telegram_profile_label


def make_access(*admin_ids: int) -> AdminAccess:
    context = SimpleNamespace(settings=SimpleNamespace(admin_ids=frozenset(admin_ids)))
    return AdminAccess(context)


def make_message(user_id: int | None, chat_type: str = "private") -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id) if user_id is not None else None,
        chat=SimpleNamespace(id=100, type=chat_type),
        content_type="text",
        answer=AsyncMock(),
    )


class AccessAndPresentationTests(unittest.TestCase):
    def test_non_admin_message_is_silently_ignored(self) -> None:
        access = make_access(1)
        message = make_message(2)

        allowed = asyncio.run(access.guard_message(message))

        self.assertFalse(allowed)
        message.answer.assert_not_awaited()

    def test_admin_group_message_is_silently_ignored(self) -> None:
        access = make_access(1)
        message = make_message(1, "group")

        allowed = asyncio.run(access.guard_message(message))

        self.assertFalse(allowed)
        message.answer.assert_not_awaited()

    def test_admin_private_message_is_allowed(self) -> None:
        access = make_access(1)
        message = make_message(1)

        allowed = asyncio.run(access.guard_message(message))

        self.assertTrue(allowed)
        message.answer.assert_not_awaited()

    def test_reminder_offset_is_human_readable(self) -> None:
        self.assertEqual(reminder_offset_label(30), "за 30 мин.")
        self.assertEqual(reminder_offset_label(120), "за 2 ч.")
        self.assertEqual(reminder_offset_label(1440), "за 1 дн.")

    def test_telegram_profile_prefers_username(self) -> None:
        self.assertEqual(
            telegram_profile_label({
                "telegram_username": "ivan",
                "telegram_first_name": "Ваня",
                "telegram_last_name": None,
            }),
            "@ivan",
        )

    def test_telegram_profile_falls_back_to_display_name(self) -> None:
        self.assertEqual(
            telegram_profile_label({
                "telegram_username": None,
                "telegram_first_name": "Пирожок",
                "telegram_last_name": "Японский",
            }),
            "Пирожок Японский",
        )
