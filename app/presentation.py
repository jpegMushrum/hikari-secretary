from __future__ import annotations

import logging
from pathlib import Path

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import User

log = logging.getLogger(__name__)


def post_title(text: str) -> str:
    clean = " ".join(text.strip().split())
    return (clean[:77] + "...") if len(clean) > 80 else (clean or "Без названия")


def telegram_identity_values(user: User) -> tuple[str | None, str | None, str | None]:
    return user.username, user.first_name, user.last_name


def telegram_profile_label(profile: dict) -> str:
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


def remove_media(paths: list[str]) -> None:
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            log.warning("Could not remove media file %s", path, exc_info=True)


def friendly_delivery_error(error: Exception) -> str:
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
