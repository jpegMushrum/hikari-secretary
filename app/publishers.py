from __future__ import annotations

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto

from .db import Delivery
from .formatting import entities_from_json
from .keyboards import registration_link_keyboard


class TelegramPublisher:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def publish(self, delivery: Delivery, registration_url: str | None = None) -> str:
        chat_id: int | str = int(delivery.destination) if delivery.destination.lstrip("-").isdigit() else delivery.destination
        entities = entities_from_json(delivery.entities)
        paths = delivery.media_paths
        last_id = 0
        thread = delivery.message_thread_id
        markup = registration_link_keyboard(registration_url) if registration_url else None
        if not paths:
            message = await self.bot.send_message(
                chat_id, delivery.text, entities=entities or None,
                message_thread_id=thread, reply_markup=markup,
            )
            return str(message.message_id)

        if len(paths) == 1:
            if len(delivery.text) <= 1024:
                message = await self.bot.send_photo(
                    chat_id, FSInputFile(paths[0]), caption=delivery.text or None,
                    caption_entities=entities or None, message_thread_id=thread,
                    reply_markup=markup,
                )
                return str(message.message_id)
            text_message = await self.bot.send_message(
                chat_id, delivery.text, entities=entities or None,
                message_thread_id=thread, reply_markup=markup,
            )
            photo_message = await self.bot.send_photo(
                chat_id, FSInputFile(paths[0]), message_thread_id=thread,
            )
            return str(photo_message.message_id or text_message.message_id)

        if delivery.text:
            message = await self.bot.send_message(
                chat_id, delivery.text, entities=entities or None,
                message_thread_id=thread, reply_markup=markup,
            )
            last_id = message.message_id
        media = [InputMediaPhoto(media=FSInputFile(path)) for path in paths]
        messages = await self.bot.send_media_group(chat_id, media, message_thread_id=thread)
        last_id = messages[-1].message_id if messages else last_id
        if registration_url and not delivery.text:
            prompt = await self.bot.send_message(
                chat_id, "Регистрация на мероприятие",
                message_thread_id=thread, reply_markup=markup,
            )
            last_id = prompt.message_id
        return str(last_id)
