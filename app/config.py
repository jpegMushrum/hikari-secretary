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

    def matches(self, chat_id: int, message_thread_id: int | None = None) -> bool:
        """Return whether an incoming Telegram update belongs to this target."""
        if self.destination != str(chat_id):
            return False
        if self.message_thread_id is None:
            return True
        return self.message_thread_id == message_thread_id


@dataclass(frozen=True, slots=True)
class AiTopicSettings:
    target: Target | None
    question_count: int
    vocabulary_count: int
    grammar_count: int


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
    reminder_options_minutes: tuple[int, ...]
    deepseek_api_key: str | None
    deepseek_model: str
    deepseek_base_url: str
    deepseek_timeout_seconds: int
    ai_topics: AiTopicSettings


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

    reminder_options_raw = os.getenv(
        "REMINDER_OPTIONS_MINUTES", "30,60,120,360,1440"
    )
    try:
        reminder_options = tuple(dict.fromkeys(
            int(value.strip())
            for value in reminder_options_raw.split(",")
            if value.strip()
        ))
    except ValueError as exc:
        raise ValueError(
            "REMINDER_OPTIONS_MINUTES должен содержать минуты через запятую"
        ) from exc
    if not reminder_options or any(value <= 0 for value in reminder_options):
        raise ValueError("REMINDER_OPTIONS_MINUTES должен содержать положительные числа")

    targets = _load_targets(targets_path)
    target_key = os.getenv("AI_TOPIC_TARGET_KEY", "").strip()
    ai_target = next((target for target in targets if target.key == target_key), None)
    if target_key and ai_target is None:
        raise ValueError(
            f"AI_TOPIC_TARGET_KEY ссылается на неизвестную цель: {target_key}"
        )
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "").strip() or None
    if deepseek_api_key and ai_target is None:
        raise ValueError(
            "При заданном DEEPSEEK_API_KEY необходимо указать AI_TOPIC_TARGET_KEY"
        )

    def bounded_int(name: str, default: int, upper: int) -> int:
        try:
            value = int(os.getenv(name, str(default)))
        except ValueError as exc:
            raise ValueError(f"{name} должен быть целым числом") from exc
        if not 1 <= value <= upper:
            raise ValueError(f"{name} должен быть от 1 до {upper}")
        return value

    return Settings(
        telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
        admin_ids=admin_ids,
        timezone=timezone,
        timezone_name=timezone_name,
        database_path=database_path,
        media_dir=media_dir,
        targets=targets,
        scheduler_interval_seconds=max(1, int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "5"))),
        max_delivery_attempts=max(1, int(os.getenv("MAX_DELIVERY_ATTEMPTS", "5"))),
        reminder_options_minutes=reminder_options,
        deepseek_api_key=deepseek_api_key,
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip(),
        deepseek_base_url=os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        ).strip().rstrip("/"),
        deepseek_timeout_seconds=max(
            1, int(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "90"))
        ),
        ai_topics=AiTopicSettings(
            target=ai_target,
            question_count=bounded_int("AI_TOPIC_QUESTION_COUNT", 5, 8),
            vocabulary_count=bounded_int("AI_TOPIC_VOCABULARY_COUNT", 10, 20),
            grammar_count=bounded_int("AI_TOPIC_GRAMMAR_COUNT", 3, 8),
        ),
    )
