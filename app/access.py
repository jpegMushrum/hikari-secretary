from __future__ import annotations

import logging

from aiogram.types import CallbackQuery, Message

from .runtime import AppContext

log = logging.getLogger(__name__)


class AdminAccess:
    def __init__(self, context: AppContext):
        self.context = context

    def is_admin(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self.context.settings.admin_ids

    async def guard_message(self, message: Message) -> bool:
        if not self.is_admin(message.from_user.id if message.from_user else None):
            log.info(
                "Admin message ignored: reason=not_admin user_id=%s chat_id=%s content_type=%s",
                message.from_user.id if message.from_user else None,
                message.chat.id,
                message.content_type,
            )
            return False
        if message.chat.type != "private":
            log.info(
                "Admin message ignored: reason=not_private user_id=%s chat_id=%s chat_type=%s",
                message.from_user.id if message.from_user else None,
                message.chat.id,
                message.chat.type,
            )
            return False
        return True

    async def guard_callback(self, callback: CallbackQuery) -> bool:
        if (
            not self.is_admin(callback.from_user.id)
            or not callback.message
            or callback.message.chat.type != "private"
        ):
            log.info(
                "Admin callback rejected: user_id=%s data=%r",
                callback.from_user.id,
                callback.data,
            )
            await callback.answer("Доступ запрещён", show_alert=True)
            return False
        return True
