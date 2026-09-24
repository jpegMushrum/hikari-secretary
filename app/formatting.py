from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from aiogram.types import InputRichMessage, MessageEntity, RichMessage


def entities_to_json(entities: Iterable[MessageEntity] | None) -> list[dict]:
    if not entities:
        return []
    return [entity.model_dump(mode="json", exclude_none=True) for entity in entities]


def entities_from_json(items: list[dict]) -> list[MessageEntity]:
    return [MessageEntity.model_validate(item) for item in items]


def rich_message_to_json(message: RichMessage | None) -> dict | None:
    if message is None:
        return None
    return message.model_dump(mode="json", exclude_none=True)


def rich_message_from_json(
    item: dict, registration_url: str | None = None
) -> InputRichMessage:
    converted = _convert_rich_media(item)
    if registration_url:
        converted["blocks"] = [
            *converted.get("blocks", []),
            {
                "type": "buttons",
                "buttons": [
                    {
                        "text": "Зарегистрироваться",
                        "url": registration_url,
                        "style": "success",
                    }
                ],
            },
        ]
    return InputRichMessage.model_validate(converted)


def _convert_rich_media(value):
    if isinstance(value, list):
        return [_convert_rich_media(item) for item in value]
    if not isinstance(value, dict):
        return value

    converted = {key: _convert_rich_media(item) for key, item in value.items()}
    block_type = converted.get("type")
    media_field = {
        "animation": "animation",
        "audio": "audio",
        "document": "document",
        "photo": "photo",
        "video": "video",
        "voice_note": "voice_note",
    }.get(block_type)
    if not media_field or media_field not in converted:
        return converted

    media = converted[media_field]
    if media_field == "photo" and isinstance(media, list):
        if not media:
            raise ValueError("Rich Message содержит пустой блок фотографии")
        media = max(
            media,
            key=lambda photo: (
                int(photo.get("file_size") or 0),
                int(photo.get("width") or 0) * int(photo.get("height") or 0),
            ),
        )
    if not isinstance(media, dict) or not media.get("file_id"):
        raise ValueError(f"Rich Message содержит неподдерживаемый медиаблок: {block_type}")
    input_media = {"media": media["file_id"]}
    if converted.pop("has_spoiler", None):
        input_media["has_spoiler"] = True
    converted[media_field] = input_media
    return converted


def rich_message_preview(item: dict | None) -> str:
    if not item:
        return ""
    parts: list[str] = []

    def collect(value) -> None:
        if isinstance(value, list):
            for child in value:
                collect(child)
            return
        if not isinstance(value, dict):
            return
        text = value.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
        elif isinstance(text, (dict, list)):
            collect(text)
        alternative_text = value.get("alternative_text")
        if isinstance(alternative_text, str) and alternative_text.strip():
            parts.append(alternative_text.strip())
        for key in ("blocks", "items", "caption"):
            if key in value:
                collect(value[key])

    collect(item.get("blocks", []))
    return "\n".join(parts)


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
