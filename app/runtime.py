from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message

from .config import Settings
from .db import Database


@dataclass(slots=True)
class AlbumBuffer:
    messages: list[Message] = field(default_factory=list)
    task: asyncio.Task | None = None


@dataclass(slots=True)
class EventSetup:
    post_id: int
    starts_at: datetime | None = None


@dataclass(slots=True)
class RuntimeState:
    albums: dict[tuple[int, str], AlbumBuffer] = field(default_factory=dict)
    awaiting_schedule: dict[int, int] = field(default_factory=dict)
    awaiting_event: dict[int, EventSetup] = field(default_factory=dict)


@dataclass(slots=True)
class AppContext:
    settings: Settings
    bot: Bot
    db: Database
    state: RuntimeState = field(default_factory=RuntimeState)
    bot_username: str | None = None
