from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto

from .db import Delivery
from .formatting import entities_from_json, rich_message_from_json


log = logging.getLogger(__name__)


class TelegramPublisher:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def publish(self, delivery: Delivery, registration_url: str | None = None) -> str:
        chat_id: int | str = int(delivery.destination) if delivery.destination.lstrip("-").isdigit() else delivery.destination
        entities = entities_from_json(delivery.entities)
        paths = delivery.media_paths
        last_id = 0
        thread = delivery.message_thread_id
        text = delivery.text
        if registration_url and not delivery.rich_message:
            separator = "\n\n" if text else ""
            text = f"{text}{separator}Регистрация: {registration_url}"
        log.info(
            "Telegram publish started: delivery_id=%s post_id=%s target=%s destination=%s "
            "thread_id=%s text_len=%s media_count=%s entities=%s registration=%s",
            delivery.id,
            delivery.post_id,
            delivery.target_key,
            delivery.destination,
            thread,
            len(delivery.text),
            len(paths),
            [str(entity.type) for entity in entities],
            registration_url is not None,
        )
        if delivery.rich_message:
            rich_message = rich_message_from_json(
                delivery.rich_message, registration_url
            )
            message = await self.bot.send_rich_message(
                chat_id,
                rich_message,
                message_thread_id=thread,
            )
            log.info(
                "Telegram publish completed: delivery_id=%s message_id=%s mode=rich_message",
                delivery.id,
                message.message_id,
            )
            return str(message.message_id)
        if not paths:
            message = await self.bot.send_message(
                chat_id, text, entities=entities or None,
                message_thread_id=thread,
            )
            log.info(
                "Telegram publish completed: delivery_id=%s message_id=%s mode=text",
                delivery.id,
                message.message_id,
            )
            return str(message.message_id)

        if len(paths) == 1:
            if len(text) <= 1024:
                message = await self.bot.send_photo(
                    chat_id, FSInputFile(paths[0]), caption=text or None,
                    caption_entities=entities or None, message_thread_id=thread,
                )
                log.info(
                    "Telegram publish completed: delivery_id=%s message_id=%s mode=photo",
                    delivery.id,
                    message.message_id,
                )
                return str(message.message_id)
            text_message = await self.bot.send_message(
                chat_id, text, entities=entities or None,
                message_thread_id=thread,
            )
            photo_message = await self.bot.send_photo(
                chat_id, FSInputFile(paths[0]), message_thread_id=thread,
            )
            result_id = photo_message.message_id or text_message.message_id
            log.info(
                "Telegram publish completed: delivery_id=%s message_id=%s mode=text_and_photo",
                delivery.id,
                result_id,
            )
            return str(result_id)

        if text:
            message = await self.bot.send_message(
                chat_id, text, entities=entities or None,
                message_thread_id=thread,
            )
            last_id = message.message_id
        media = [InputMediaPhoto(media=FSInputFile(path)) for path in paths]
        messages = await self.bot.send_media_group(chat_id, media, message_thread_id=thread)
        last_id = messages[-1].message_id if messages else last_id
        log.info(
            "Telegram publish completed: delivery_id=%s message_id=%s mode=album",
            delivery.id,
            last_id,
        )
        return str(last_id)
