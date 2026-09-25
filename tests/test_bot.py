import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot import SecretaryBot


def make_bot(*admin_ids: int) -> SecretaryBot:
    bot = object.__new__(SecretaryBot)
    bot.settings = SimpleNamespace(
        admin_ids=frozenset(admin_ids), event_reminder_hours=2
    )
    return bot


def make_message(user_id: int | None, chat_type: str = "private") -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id) if user_id is not None else None,
        chat=SimpleNamespace(type=chat_type),
        answer=AsyncMock(),
    )


def test_non_admin_message_is_silently_ignored() -> None:
    bot = make_bot(1)
    message = make_message(2)

    allowed = asyncio.run(bot._guard_message(message))

    assert allowed is False
    message.answer.assert_not_awaited()


def test_admin_group_message_is_silently_ignored() -> None:
    bot = make_bot(1)
    message = make_message(1, "group")

    allowed = asyncio.run(bot._guard_message(message))

    assert allowed is False
    message.answer.assert_not_awaited()


def test_admin_private_message_is_allowed() -> None:
    bot = make_bot(1)
    message = make_message(1)

    allowed = asyncio.run(bot._guard_message(message))

    assert allowed is True
    message.answer.assert_not_awaited()


def test_reminder_question_uses_configured_hours() -> None:
    bot = make_bot(1)

    assert bot._reminder_question() == "Напомнить вам о мероприятии за 2 ч. до начала?"


def test_telegram_profile_prefers_username() -> None:
    assert SecretaryBot._telegram_profile_label({
        "telegram_username": "ivan",
        "telegram_first_name": "Ваня",
        "telegram_last_name": None,
    }) == "@ivan"


def test_telegram_profile_falls_back_to_display_name() -> None:
    assert SecretaryBot._telegram_profile_label({
        "telegram_username": None,
        "telegram_first_name": "Пирожок",
        "telegram_last_name": "Японский",
    }) == "Пирожок Японский"
