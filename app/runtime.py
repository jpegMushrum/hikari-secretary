from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message

from .config import Settings
from .db import Database
from .services.daily_topics import DailyTopic


@dataclass(slots=True)
class AlbumBuffer:
    messages: list[Message] = field(default_factory=list)
    task: asyncio.Task | None = None


@dataclass(slots=True)
class EventSetup:
    post_id: int
    title: str | None = None
    starts_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AiTopicPreview:
    token: str
    topic: DailyTopic


@dataclass(slots=True)
class AiTopicAdminOptions:
    jlpt_level: str
    comment: str | None = None
    awaiting_comment: bool = False


@dataclass(slots=True)
class RuntimeState:
    albums: dict[tuple[int, str], AlbumBuffer] = field(default_factory=dict)
    awaiting_schedule: dict[int, int] = field(default_factory=dict)
    awaiting_event: dict[int, EventSetup] = field(default_factory=dict)
    ai_topic_previews: dict[int, AiTopicPreview] = field(default_factory=dict)
    ai_topic_options: dict[int, AiTopicAdminOptions] = field(default_factory=dict)


@dataclass(slots=True)
class AppContext:
    settings: Settings
    bot: Bot
    db: Database
    state: RuntimeState = field(default_factory=RuntimeState)
    bot_username: str | None = None
