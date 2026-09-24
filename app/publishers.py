from __future__ import annotations

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto

from .db import Delivery
from .formatting import entities_from_json


class TelegramPublisher:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def publish(self, delivery: Delivery) -> str:
        chat_id: int | str = int(delivery.destination) if delivery.destination.lstrip("-").isdigit() else delivery.destination
        entities = entities_from_json(delivery.entities)
        paths = delivery.media_paths
        last_id = 0
        thread = delivery.message_thread_id
        if not paths:
            message = await self.bot.send_message(
                chat_id, delivery.text, entities=entities or None, message_thread_id=thread
            )
            return str(message.message_id)

        if len(paths) == 1 and len(delivery.text) <= 1024:
            message = await self.bot.send_photo(
                chat_id, FSInputFile(paths[0]), caption=delivery.text or None,
                caption_entities=entities or None, message_thread_id=thread,
            )
            return str(message.message_id)

        if delivery.text:
            message = await self.bot.send_message(
                chat_id, delivery.text, entities=entities or None, message_thread_id=thread
            )
            last_id = message.message_id
        media = [InputMediaPhoto(media=FSInputFile(path)) for path in paths]
        messages = await self.bot.send_media_group(chat_id, media, message_thread_id=thread)
        return str(messages[-1].message_id if messages else last_id)
