from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from aiogram.types import MessageEntity


STYLE_ENTITY_TYPES = {
    "bold",
    "italic",
    "underline",
    "strikethrough",
    "spoiler",
    "code",
    "pre",
    "blockquote",
    "expandable_blockquote",
}


def entities_to_json(entities: Iterable[MessageEntity] | None) -> list[dict]:
    if not entities:
        return []
    return [entity.model_dump(mode="json", exclude_none=True) for entity in entities]


def entities_from_json(items: list[dict]) -> list[MessageEntity]:
    return [MessageEntity.model_validate(item) for item in items]


def formatting_loss(items: list[dict]) -> bool:
    return any(str(item.get("type")) in STYLE_ENTITY_TYPES for item in items)


def _utf16_offset_to_index(text: str, offset: int) -> int:
    """Convert Telegram's UTF-16 entity offset to a Python string index."""
    return len(text.encode("utf-16-le")[: offset * 2].decode("utf-16-le"))


def render_vk_text(text: str, entities: list[dict]) -> str:
    """Preserve Telegram text-link destinations in VK's plain-text post body."""
    insertions: list[tuple[int, str]] = []
    for entity in entities:
        if str(entity.get("type")) != "text_link" or not entity.get("url"):
            continue
        start = _utf16_offset_to_index(text, int(entity["offset"]))
        end = _utf16_offset_to_index(text, int(entity["offset"]) + int(entity["length"]))
        url = str(entity["url"])
        if text[start:end].strip() != url:
            insertions.append((end, f" ({url})"))
    result = text
    for index, addition in sorted(insertions, reverse=True):
        result = result[:index] + addition + result[index:]
    return result


def parse_schedule(value: str, local_tz: ZoneInfo, now: datetime | None = None) -> datetime:
    clean = " ".join(value.strip().split())
    local_now = (now or datetime.now(timezone.utc)).astimezone(local_tz)
    parsed: datetime | None = None
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%y %H:%M"):
        try:
            parsed = datetime.strptime(clean, fmt)
            break
        except ValueError:
            pass
    if parsed is None:
        try:
            short = datetime.strptime(clean, "%d.%m %H:%M")
            parsed = short.replace(year=local_now.year)
            candidate = parsed.replace(tzinfo=local_tz)
            if candidate <= local_now:
                parsed = parsed.replace(year=local_now.year + 1)
        except ValueError as exc:
            raise ValueError("Используйте формат ДД.ММ.ГГГГ ЧЧ:ММ") from exc
    aware = parsed.replace(tzinfo=local_tz)
    if aware <= local_now:
        raise ValueError("Время публикации должно быть в будущем")
    return aware.astimezone(timezone.utc)


def format_local(utc_iso: str, local_tz: ZoneInfo) -> str:
    return datetime.fromisoformat(utc_iso).astimezone(local_tz).strftime("%d.%m.%Y %H:%M")
