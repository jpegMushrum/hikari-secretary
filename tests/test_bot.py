import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from app.access import AdminAccess
from app.handlers.registrations import RegistrationHandlers
from app.db import Page
from app.presentation import (
    participant_status_label,
    participants_rich_message,
    reminder_offset_label,
    telegram_profile_label,
)


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

    def test_participant_table_uses_rich_message_table_block(self) -> None:
        message = participants_rich_message(
            7,
            "Осенний вечер японского языка",
            [{
                "full_name": "Анна Петрова",
                "telegram_username": None,
                "telegram_first_name": "Анна",
                "telegram_last_name": "Петрова",
                "status": "cancelled",
                "attended": None,
                "registered_at": datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc).isoformat(),
                "cancelled_at": datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc).isoformat(),
                "is_russian_citizen": 1,
                "is_itmo_student": 0,
            }],
            0,
            1,
            ZoneInfo("Europe/Moscow"),
        )

        table = message.blocks[1]
        self.assertEqual(
            message.blocks[0].text,
            "Участники мероприятия #7: «Осенний вечер японского языка»",
        )
        self.assertEqual(table.type, "table")
        self.assertEqual(table.cells[0][0].text, "ФИО")
        self.assertEqual(table.cells[1][1].text, "Анна Петрова")
        self.assertEqual(table.cells[1][2].text, "отменён")
        self.assertEqual(table.cells[1][3].text, "02.10.2026 13:00")
        self.assertEqual(table.cells[1][4].text, "✅")
        self.assertEqual(table.cells[1][5].text, "❌")

    def test_participant_statuses_are_human_readable(self) -> None:
        self.assertEqual(
            participant_status_label({"status": "registered", "attended": None}),
            "зарегистрирован",
        )
        self.assertEqual(
            participant_status_label({"status": "cancelled", "attended": None}),
            "отменён",
        )
        self.assertEqual(
            participant_status_label({"status": "registered", "attended": 1}),
            "был",
        )
        self.assertEqual(
            participant_status_label({"status": "registered", "attended": 0}),
            "не был",
        )

    def test_participant_table_is_sent_only_after_admin_guard(self) -> None:
        context = SimpleNamespace(
            settings=SimpleNamespace(timezone=ZoneInfo("Europe/Moscow")),
            db=SimpleNamespace(event_registrations_page=AsyncMock(return_value=Page([{
                "full_name": "Анна Петрова",
                "title": "Осенний вечер японского языка",
                "text": "Описание мероприятия",
                "telegram_username": "anna",
                "telegram_first_name": "Анна",
                "telegram_last_name": "Петрова",
                "status": "registered",
                "attended": None,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "cancelled_at": None,
                "is_russian_citizen": 1,
                "is_itmo_student": 0,
            }], 0, 10, 1))),
            bot=SimpleNamespace(send_rich_message=AsyncMock()),
        )
        access = SimpleNamespace(guard_callback=AsyncMock(return_value=True))
        handlers = RegistrationHandlers(context, access)
        callback = SimpleNamespace(
            data="participants:7",
            message=SimpleNamespace(chat=SimpleNamespace(id=1), answer=AsyncMock()),
            answer=AsyncMock(),
        )

        asyncio.run(handlers.show_participants(callback))

        context.db.event_registrations_page.assert_awaited_once_with(7, 0)
        context.bot.send_rich_message.assert_awaited_once()
        self.assertEqual(
            context.bot.send_rich_message.await_args.args[1].blocks[1].type,
            "table",
        )
        callback.answer.assert_awaited_once()
