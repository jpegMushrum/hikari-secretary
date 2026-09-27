from __future__ import annotations

from datetime import datetime

from ..config import Target
from ..db import Database, DeliveryTarget


class PublicationService:
    """Application boundary for creating and scheduling publications."""

    def __init__(self, db: Database, targets: tuple[Target, ...]):
        self.db = db
        self.targets = {target.key: target for target in targets}

    async def create_draft(
        self,
        creator_id: int,
        text: str,
        entities: list[dict],
        media_paths: list[str],
        rich_message: dict | None = None,
    ) -> int:
        return await self.db.create_post(
            creator_id, text, entities, media_paths, rich_message
        )

    async def toggle_target(self, post_id: int, target: Target) -> None:
        await self.db.toggle_delivery(
            post_id,
            target.key,
            target.name,
            target.destination,
            target.message_thread_id,
        )

    async def schedule(self, post_id: int, when: datetime) -> bool:
        return await self.db.schedule(post_id, when)

    async def create_scheduled(
        self,
        *,
        creator_id: int,
        text: str,
        target_keys: tuple[str, ...],
        scheduled_at: datetime,
        source: str,
        idempotency_key: str | None = None,
        entities: list[dict] | None = None,
        media_paths: list[str] | None = None,
        rich_message: dict | None = None,
    ) -> int:
        unknown = [key for key in target_keys if key not in self.targets]
        if unknown:
            raise ValueError(f"Неизвестные цели публикации: {', '.join(unknown)}")
        selected = tuple(
            DeliveryTarget(
                key=self.targets[key].key,
                name=self.targets[key].name,
                destination=self.targets[key].destination,
                message_thread_id=self.targets[key].message_thread_id,
            )
            for key in dict.fromkeys(target_keys)
        )
        return await self.db.create_scheduled_post(
            creator_id,
            text,
            entities or [],
            media_paths or [],
            selected,
            scheduled_at,
            source=source,
            source_key=idempotency_key,
            rich_message=rich_message,
        )
