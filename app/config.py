from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class Target:
    index: int
    key: str
    name: str
    destination: str
    message_thread_id: int | None = None


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    admin_ids: frozenset[int]
    timezone: ZoneInfo
    timezone_name: str
    database_path: Path
    media_dir: Path
    targets: tuple[Target, ...]
    scheduler_interval_seconds: int
    max_delivery_attempts: int
    event_reminder_hours: int


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Переменная окружения {name} не задана")
    return value


def _load_targets(path: Path) -> tuple[Target, ...]:
    try:
        raw: dict[str, list[dict[str, Any]]] = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Файл целей не найден: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Некорректный JSON в {path}: {exc}") from exc

    targets: list[Target] = []
    keys: set[str] = set()
    for item in raw.get("telegram", []):
        key = str(item.get("key", "")).strip()
        name = str(item.get("name", "")).strip()
        destination = str(item.get("chat_id", "")).strip()
        if not key or not name or not destination:
            raise ValueError("У цели Telegram обязательны key, name и chat_id")
        if key in keys:
            raise ValueError(f"Ключ цели должен быть уникальным: {key}")
        keys.add(key)
        thread_id: int | None = None
        if item.get("message_thread_id") is not None:
            try:
                thread_id = int(item["message_thread_id"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"message_thread_id цели {key} должен быть числом") from exc
            if thread_id <= 0:
                raise ValueError(f"message_thread_id цели {key} должен быть положительным")
        targets.append(Target(len(targets), key, name, destination, thread_id))
    if not targets:
        raise ValueError("В targets.json не задано ни одной цели")
    return tuple(targets)


def load_settings() -> Settings:
    admin_ids_raw = _required("ADMIN_IDS")
    try:
        admin_ids = frozenset(int(value.strip()) for value in admin_ids_raw.split(",") if value.strip())
    except ValueError as exc:
        raise ValueError("ADMIN_IDS должен содержать Telegram ID через запятую") from exc
    if not admin_ids:
        raise ValueError("ADMIN_IDS не должен быть пустым")

    timezone_name = os.getenv("TIMEZONE", "Europe/Moscow").strip()
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Неизвестный часовой пояс: {timezone_name}") from exc

    targets_path = Path(os.getenv("TARGETS_PATH", "/app/targets.json"))
    database_path = Path(os.getenv("DATABASE_PATH", "/app/data/bot.sqlite3"))
    media_dir = Path(os.getenv("MEDIA_DIR", "/app/data/media"))
    database_path.parent.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
        admin_ids=admin_ids,
        timezone=timezone,
        timezone_name=timezone_name,
        database_path=database_path,
        media_dir=media_dir,
        targets=_load_targets(targets_path),
        scheduler_interval_seconds=max(1, int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "5"))),
        max_delivery_attempts=max(1, int(os.getenv("MAX_DELIVERY_ATTEMPTS", "5"))),
        event_reminder_hours=max(1, int(os.getenv("EVENT_REMINDER_HOURS", "24"))),
    )
