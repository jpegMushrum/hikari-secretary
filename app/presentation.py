from __future__ import annotations

import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InputRichMessage, User

from .formatting import format_local

log = logging.getLogger(__name__)


def post_title(text: str) -> str:
    clean = " ".join(text.strip().split())
    return (clean[:77] + "...") if len(clean) > 80 else (clean or "Без названия")


def event_title(event: dict) -> str:
    title = " ".join((event.get("title") or "").strip().split())
    return title or post_title(event.get("text") or "")


def reminder_offset_label(minutes: int | None) -> str:
    if minutes is None:
        return "выключено"
    if minutes < 60:
        return f"за {minutes} мин."
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"за {days} дн."
    if minutes % 60 == 0:
        return f"за {minutes // 60} ч."
    return f"за {minutes // 60} ч. {minutes % 60} мин."


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


def participant_status_label(participant: dict) -> str:
    if participant["status"] == "cancelled":
        return "отменён"
    if participant["attended"] is True or participant["attended"] == 1:
        return "был"
    if participant["attended"] is False or participant["attended"] == 0:
        return "не был"
    return "зарегистрирован"


def _yes_no_table_value(value: int | None) -> str:
    if value is None:
        return "—"
    return "✅" if value else "❌"


def _short_table_value(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    return f"{clean[:limit - 1]}…" if len(clean) > limit else (clean or "—")


def _table_cell(text: str, *, header: bool = False) -> dict:
    return {
        "text": text,
        "align": "left",
        "valign": "top",
        "is_header": header,
    }


def participants_rich_message(
    post_id: int,
    title: str,
    participants: list[dict],
    page: int,
    pages: int,
    local_tz: ZoneInfo,
) -> InputRichMessage:
    cells = [[
        _table_cell("ФИО", header=True),
        _table_cell("Telegram", header=True),
        _table_cell("Статус", header=True),
        _table_cell("Время\nрег./отм.", header=True),
        _table_cell("РФ", header=True),
        _table_cell("ИТМО", header=True),
    ]]
    for participant in participants:
        timestamp = (
            participant["cancelled_at"]
            if participant["status"] == "cancelled"
            else participant["registered_at"]
        )
        cells.append([
            _table_cell(_short_table_value(participant["full_name"], 32)),
            _table_cell(_short_table_value(telegram_profile_label(participant), 24)),
            _table_cell(participant_status_label(participant)),
            _table_cell(format_local(timestamp, local_tz) if timestamp else "—"),
            _table_cell(_yes_no_table_value(participant["is_russian_citizen"])),
            _table_cell(_yes_no_table_value(participant["is_itmo_student"])),
        ])
    return InputRichMessage.model_validate({
        "blocks": [
            {
                "type": "heading",
                "text": f"Участники мероприятия #{post_id}: «{title}»",
                "size": 2,
            },
            {
                "type": "table",
                "caption": f"Страница {page + 1}/{pages}",
                "cells": cells,
                "is_bordered": True,
                "is_striped": True,
                "is_compact": True,
            },
        ]
    })


def feedback_author_label(feedback: dict) -> str:
    full_name = " ".join((feedback.get("full_name") or "").split())
    if full_name:
        return f"{full_name} ({telegram_profile_label(feedback)})"
    telegram = telegram_profile_label(feedback)
    if telegram != "имя профиля не указано":
        return telegram
    return f"Пользователь #{feedback['user_id']}"


def feedback_event_label(feedback: dict) -> str:
    if feedback.get("post_id") is None:
        return "Общий отзыв (мероприятие не указано)"
    return (
        f"Мероприятие #{feedback['post_id']}: "
        f"«{event_title({'title': feedback.get('title'), 'text': feedback.get('post_text')})}»"
    )


def _short_feedback_text(text: str, limit: int = 500) -> str:
    clean = text.strip()
    return f"{clean[:limit - 1]}…" if len(clean) > limit else clean


def feedbacks_list_text(feedback_entries: list[dict], page: int, pages: int, local_tz: ZoneInfo) -> str:
    lines = [f"💬 Отзывы · страница {page + 1}/{pages}"]
    if not feedback_entries:
        return "\n".join([*lines, "", "Отзывов пока нет."])
    for index, feedback in enumerate(feedback_entries, 1):
        lines.extend((
            f"\n{index}. {_short_feedback_text(feedback_author_label(feedback), 80)}",
            f"   {format_local(feedback['created_at'], local_tz)}",
            f"   {_short_feedback_text(feedback_event_label(feedback), 140)}",
            _short_feedback_text(feedback["feedback_text"], 350),
        ))
    return "\n".join(lines)


def feedback_detail_text(feedback: dict, local_tz: ZoneInfo) -> str:
    return "\n".join((
        f"💬 Отзыв #{feedback['id']}",
        "",
        f"Автор: {feedback_author_label(feedback)}",
        f"Время: {format_local(feedback['created_at'], local_tz)}",
        feedback_event_label(feedback),
        "",
        feedback["feedback_text"],
    ))


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
