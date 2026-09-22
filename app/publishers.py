from __future__ import annotations

import json
import zlib
from pathlib import Path

import aiohttp
from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto

from .db import Delivery
from .formatting import entities_from_json, render_vk_text


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


class VKPublisher:
    API_URL = "https://api.vk.com/method"

    def __init__(self, access_token: str, api_version: str, session: aiohttp.ClientSession):
        self.access_token = access_token
        self.api_version = api_version
        self.session = session

    async def _method(self, method: str, **params):
        payload = params | {"access_token": self.access_token, "v": self.api_version}
        async with self.session.post(f"{self.API_URL}/{method}", data=payload) as response:
            data = await response.json(content_type=None)
        if "error" in data:
            error = data["error"]
            raise RuntimeError(f"VK {error.get('error_code')}: {error.get('error_msg')}")
        return data["response"]

    async def _upload_photo(self, group_id: int, path: str) -> str:
        server = await self._method("photos.getWallUploadServer", group_id=group_id)
        form = aiohttp.FormData()
        form.add_field("photo", Path(path).open("rb"), filename=Path(path).name, content_type="image/jpeg")
        async with self.session.post(server["upload_url"], data=form) as response:
            uploaded = await response.json(content_type=None)
        saved = await self._method(
            "photos.saveWallPhoto", group_id=group_id, photo=uploaded["photo"],
            server=uploaded["server"], hash=uploaded["hash"],
        )
        photo = saved[0]
        attachment = f"photo{photo['owner_id']}_{photo['id']}"
        if photo.get("access_key"):
            attachment += f"_{photo['access_key']}"
        return attachment

    async def publish(self, delivery: Delivery) -> str:
        group_id = abs(int(delivery.destination))
        attachments = [await self._upload_photo(group_id, path) for path in delivery.media_paths]
        random_id = zlib.crc32(f"hikari:{delivery.post_id}:{delivery.target_key}".encode()) & 0x7FFFFFFF
        result = await self._method(
            "wall.post", owner_id=-group_id, from_group=1,
            message=render_vk_text(delivery.text, delivery.entities),
            attachments=",".join(attachments), random_id=random_id,
        )
        return str(result["post_id"])
