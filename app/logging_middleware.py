from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import CallbackQuery, Message, TelegramObject, Update


log = logging.getLogger(__name__)


class UpdateLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        event_type = event.event_type
        payload = getattr(event, event_type, None)
        details = self._details(payload)
        log.info(
            "Update received: id=%s type=%s%s",
            event.update_id,
            event_type,
            details,
        )
        try:
            result = await handler(event, data)
        except Exception:
            log.exception(
                "Update failed: id=%s type=%s%s",
                event.update_id,
                event_type,
                details,
            )
            raise
        log.info(
            "Update routed: id=%s type=%s handled=%s",
            event.update_id,
            event_type,
            result is not UNHANDLED,
        )
        return result

    @staticmethod
    def _details(payload: Any) -> str:
        if isinstance(payload, Message):
            entities = payload.entities or payload.caption_entities or []
            entity_types = [str(entity.type) for entity in entities]
            user_id = payload.from_user.id if payload.from_user else None
            content_type = getattr(payload.content_type, "value", payload.content_type)
            chat_type = getattr(payload.chat.type, "value", payload.chat.type)
            rich_blocks = len(payload.rich_message.blocks) if payload.rich_message else 0
            return (
                f" user_id={user_id} chat_id={payload.chat.id}"
                f" chat_type={chat_type} content_type={content_type}"
                f" text_len={len(payload.text or '')} caption_len={len(payload.caption or '')}"
                f" entities={entity_types} forwarded={payload.forward_origin is not None}"
                f" media_group={payload.media_group_id is not None} rich_blocks={rich_blocks}"
            )
        if isinstance(payload, CallbackQuery):
            chat_id = payload.message.chat.id if payload.message else None
            return (
                f" user_id={payload.from_user.id} chat_id={chat_id}"
                f" callback_data={payload.data!r}"
            )
        return ""
