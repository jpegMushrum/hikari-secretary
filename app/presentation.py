from __future__ import annotations

from html import escape
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InputRichMessage, User

from .formatting import format_local

log = logging.getLogger(__name__)

PERSON_STATISTICS_SORT_LABELS = {
    "name": "ФИО",
    "visits": "посещениям",
    "last_visit": "последнему посещению",
}

PARTICIPANT_SORT_LABELS = {
    "name": "ФИО",
    "pass": "необходимости пропуска",
    "registered_at": "времени регистрации",
}


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
    sort_by: str = "name",
) -> InputRichMessage:
    cells = [[
        _table_cell("ФИО", header=True),
        _table_cell("Telegram", header=True),
        _table_cell("Статус", header=True),
        _table_cell("РФ", header=True),
        _table_cell("ИТМО", header=True),
        _table_cell("Время\nрег./отм.", header=True),
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
            _table_cell(_yes_no_table_value(participant["is_russian_citizen"])),
            _table_cell(_yes_no_table_value(participant["is_itmo_student"])),
            _table_cell(format_local(timestamp, local_tz) if timestamp else "—"),
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
                "caption": (
                    f"Страница {page + 1}/{pages} · сортировка по "
                    f"{PARTICIPANT_SORT_LABELS[sort_by]}"
                ),
                "cells": cells,
                "is_bordered": True,
                "is_striped": True,
                "is_compact": True,
            },
        ]
    })


def admin_events_rich_message(
    events: list[dict], past: bool, page: int, pages: int, local_tz: ZoneInfo
) -> InputRichMessage:
    heading = "Прошедшие мероприятия" if past else "Активные мероприятия"
    cells = [[
        _table_cell("#", header=True),
        _table_cell("Название", header=True),
        _table_cell("Начало", header=True),
        _table_cell("Конец", header=True),
        _table_cell("Участн.", header=True),
    ]]
    for event in events:
        cells.append([
            _table_cell(str(event["post_id"])),
            _table_cell(_short_table_value(event_title(event), 48)),
            _table_cell(format_local(event["starts_at"], local_tz)),
            _table_cell(format_local(event["ends_at"], local_tz)),
            _table_cell(str(event["registrations"])),
        ])
    caption = f"Страница {page + 1}/{pages}"
    if not events:
        caption += " · список пуст"
    return InputRichMessage.model_validate({
        "blocks": [
            {"type": "heading", "text": heading, "size": 2},
            {
                "type": "table",
                "caption": caption,
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


def feedbacks_rich_message(
    feedback_entries: list[dict], page: int, pages: int, local_tz: ZoneInfo
) -> InputRichMessage:
    cells = [[
        _table_cell("Автор", header=True),
        _table_cell("Мероприятие", header=True),
        _table_cell("Время", header=True),
        _table_cell("Отзыв", header=True),
    ]]
    for feedback in feedback_entries:
        cells.append([
            _table_cell(_short_table_value(feedback_author_label(feedback), 40)),
            _table_cell(_short_table_value(feedback_event_label(feedback), 56)),
            _table_cell(format_local(feedback["created_at"], local_tz)),
            _table_cell(_short_table_value(feedback["feedback_text"], 300)),
        ])
    caption = f"Страница {page + 1}/{pages}"
    if not feedback_entries:
        caption += " · отзывов пока нет"
    return InputRichMessage.model_validate({
        "blocks": [
            {"type": "heading", "text": "Отзывы", "size": 2},
            {
                "type": "table",
                "caption": caption,
                "cells": cells,
                "is_bordered": True,
                "is_striped": True,
                "is_compact": True,
            },
        ]
    })


def feedback_detail_text(feedback: dict, local_tz: ZoneInfo) -> str:
    if feedback.get("post_id") is None:
        event = "<b>Мероприятие:</b> не указано"
    else:
        title = event_title({
            "title": feedback.get("title"),
            "text": feedback.get("post_text"),
        })
        event = f"<b>Мероприятие #{feedback['post_id']}:</b> «{escape(title)}»"
    return "\n".join((
        f"<b>💬 Отзыв #{feedback['id']}</b>",
        "",
        f"<b>Автор:</b> {escape(feedback_author_label(feedback))}",
        f"<b>Время:</b> {format_local(feedback['created_at'], local_tz)}",
        event,
        "",
        f"<i>{escape(feedback['feedback_text'])}</i>",
    ))


def people_statistics_rich_message(
    people: list[dict],
    page: int,
    pages: int,
    sort_by: str,
    local_tz: ZoneInfo,
) -> InputRichMessage:
    cells = [[
        _table_cell("ФИО", header=True),
        _table_cell("Telegram", header=True),
        _table_cell("РФ", header=True),
        _table_cell("ИТМО", header=True),
        _table_cell("Посещ.", header=True),
        _table_cell("Отзывы", header=True),
        _table_cell("Последнее\nпосещение", header=True),
    ]]
    for person in people:
        cells.append([
            _table_cell(_short_table_value(person["full_name"], 28)),
            _table_cell(_short_table_value(telegram_profile_label(person), 20)),
            _table_cell(_yes_no_table_value(person["is_russian_citizen"])),
            _table_cell(_yes_no_table_value(person["is_itmo_student"])),
            _table_cell(str(person["visits"])),
            _table_cell(str(person["feedback_count"])),
            _table_cell(
                format_local(person["last_visited_at"], local_tz)
                if person["last_visited_at"] else "—"
            ),
        ])
    return InputRichMessage.model_validate({
        "blocks": [
            {"type": "heading", "text": "Статистика людей", "size": 2},
            {
                "type": "table",
                "caption": (
                    f"Страница {page + 1}/{pages} · сортировка по "
                    f"{PERSON_STATISTICS_SORT_LABELS[sort_by]}"
                ),
                "cells": cells,
                "is_bordered": True,
                "is_striped": True,
                "is_compact": True,
            },
        ]
    })


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
