from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from .config import Settings
from .db import Database, Delivery
from .formatting import entities_to_json, format_local, formatting_loss, parse_schedule
from .keyboards import draft_keyboard, queue_cancel_keyboard
from .publishers import TelegramPublisher, VKPublisher

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Album:
    messages: list[Message] = field(default_factory=list)
    task: asyncio.Task | None = None


class SecretaryBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.bot = Bot(settings.telegram_bot_token)
        self.dp = Dispatcher()
        self.router = Router()
        self.db = Database(settings.database_path)
        self.albums: dict[tuple[int, str], Album] = {}
        self.awaiting_schedule: dict[int, int] = {}
        self.session: aiohttp.ClientSession | None = None
        self._register_handlers()
        self.dp.include_router(self.router)

    def _is_admin(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self.settings.admin_ids

    async def _guard_message(self, message: Message) -> bool:
        if not self._is_admin(message.from_user.id if message.from_user else None):
            await message.answer("Доступ запрещён.")
            return False
        if message.chat.type != "private":
            return False
        return True

    async def _guard_callback(self, callback: CallbackQuery) -> bool:
        if not self._is_admin(callback.from_user.id):
            await callback.answer("Доступ запрещён", show_alert=True)
            return False
        return True

    def _register_handlers(self) -> None:
        self.router.message.register(self.start, CommandStart())
        self.router.message.register(self.help, Command("help"))
        self.router.message.register(self.queue, Command("queue"))
        self.router.callback_query.register(self.toggle_target, F.data.startswith("target:"))
        self.router.callback_query.register(self.publish_now, F.data.startswith("now:"))
        self.router.callback_query.register(self.ask_schedule, F.data.startswith("schedule:"))
        self.router.callback_query.register(self.cancel, F.data.startswith("cancel:"))
        self.router.message.register(self.content, F.content_type.in_({"text", "photo"}))

    async def start(self, message: Message) -> None:
        if not await self._guard_message(message):
            return
        await message.answer(
            "Отправьте текст, фотографию с подписью или альбом. Затем выберите площадки и время публикации.\n\n"
            "/queue — запланированные публикации\n/help — помощь"
        )

    async def help(self, message: Message) -> None:
        if not await self._guard_message(message):
            return
        await message.answer(
            "Поддерживаются текст, ссылки и изображения. Оформляйте текст средствами Telegram — оно сохранится в Telegram, "
            "а для VK будет отправлен чистый текст со ссылками. Время вводится в формате ДД.ММ.ГГГГ ЧЧ:ММ "
            f"({self.settings.timezone_name})."
        )

    async def queue(self, message: Message) -> None:
        if not await self._guard_message(message):
            return
        rows = await self.db.queue()
        if not rows:
            await message.answer("Очередь пуста.")
            return
        for row in rows:
            await message.answer(
                f"Публикация #{row['id']}\n"
                f"Время: {format_local(row['scheduled_at'], self.settings.timezone)} ({self.settings.timezone_name})\n"
                f"Цели: {row['targets']}",
                reply_markup=queue_cancel_keyboard(row["id"]),
            )

    async def content(self, message: Message) -> None:
        if not await self._guard_message(message):
            return
        if message.from_user.id in self.awaiting_schedule and message.text:
            post_id = self.awaiting_schedule[message.from_user.id]
            try:
                when = parse_schedule(message.text, self.settings.timezone)
            except ValueError as exc:
                await message.answer(str(exc))
                return
            if await self.db.schedule(post_id, when):
                self.awaiting_schedule.pop(message.from_user.id, None)
                await message.answer(
                    f"Публикация #{post_id} запланирована на "
                    f"{when.astimezone(self.settings.timezone):%d.%m.%Y %H:%M} ({self.settings.timezone_name})."
                )
            else:
                await message.answer("Не выбрана ни одна цель или черновик уже закрыт.")
            return
        if message.media_group_id:
            key = (message.chat.id, message.media_group_id)
            album = self.albums.setdefault(key, Album())
            album.messages.append(message)
            if album.task:
                album.task.cancel()
            album.task = asyncio.create_task(self._finish_album(key))
            return
        await self._create_draft([message])

    async def _finish_album(self, key: tuple[int, str]) -> None:
        try:
            await asyncio.sleep(1)
            album = self.albums.pop(key, None)
            if album:
                album.messages.sort(key=lambda item: item.message_id)
                await self._create_draft(album.messages)
        except asyncio.CancelledError:
            return

    async def _download_photo(self, message: Message) -> str:
        photo = message.photo[-1]
        suffix = ".jpg"
        path = self.settings.media_dir / f"{uuid.uuid4().hex}{suffix}"
        await self.bot.download(photo, destination=path)
        return str(path)

    async def _create_draft(self, messages: list[Message]) -> None:
        lead = next((item for item in messages if item.caption or item.text), messages[0])
        text = lead.text or lead.caption or ""
        entities = entities_to_json(lead.entities or lead.caption_entities)
        media_paths = [await self._download_photo(item) for item in messages if item.photo]
        post_id = await self.db.create_post(lead.from_user.id, text, entities, media_paths)
        await self._show_draft(lead.chat.id, post_id)

    async def _show_draft(self, chat_id: int, post_id: int, edit: Message | None = None) -> None:
        post = await self.db.post(post_id)
        selected = {item["target_key"] for item in post["deliveries"]}
        warning = "\n\n⚠ Оформление будет упрощено в VK." if formatting_loss(post["entities"]) else ""
        text_preview = post["text"][:500] or "[без текста]"
        body = (
            f"Черновик #{post_id}\n\n{text_preview}\n\n"
            f"Изображений: {len(post['media_paths'])}\nВыберите цели публикации.{warning}"
        )
        markup = draft_keyboard(post_id, selected, self.settings)
        if edit:
            await edit.edit_text(body, reply_markup=markup)
        else:
            await self.bot.send_message(chat_id, body, reply_markup=markup)

    async def toggle_target(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        _, post_raw, index_raw = callback.data.split(":")
        post_id, index = int(post_raw), int(index_raw)
        post = await self.db.post(post_id)
        if not post or post["status"] != "draft":
            await callback.answer("Черновик уже закрыт", show_alert=True)
            return
        target = self.settings.targets[index]
        await self.db.toggle_delivery(
            post_id,
            target.platform,
            target.key,
            target.name,
            target.destination,
            target.message_thread_id,
        )
        await self._show_draft(callback.message.chat.id, post_id, callback.message)
        await callback.answer()

    async def publish_now(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        if await self.db.schedule(post_id, datetime.now(timezone.utc)):
            await callback.message.edit_text(f"Публикация #{post_id} поставлена в очередь.")
        else:
            await callback.answer("Выберите хотя бы одну цель", show_alert=True)

    async def ask_schedule(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        post = await self.db.post(post_id)
        if not post or not post["deliveries"]:
            await callback.answer("Выберите хотя бы одну цель", show_alert=True)
            return
        self.awaiting_schedule[callback.from_user.id] = post_id
        await callback.message.answer(
            f"Введите дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ. Часовой пояс: {self.settings.timezone_name}."
        )
        await callback.answer()

    async def cancel(self, callback: CallbackQuery) -> None:
        if not await self._guard_callback(callback):
            return
        post_id = int(callback.data.split(":")[1])
        self.awaiting_schedule.pop(callback.from_user.id, None)
        post = await self.db.post(post_id)
        if await self.db.cancel(post_id):
            if post:
                self._remove_media(post["media_paths"])
            await callback.message.edit_text(f"Публикация #{post_id} отменена.")
        else:
            await callback.answer("Публикацию уже нельзя отменить", show_alert=True)

    async def scheduler(self) -> None:
        telegram = TelegramPublisher(self.bot)
        vk = VKPublisher(self.settings.vk_access_token, self.settings.vk_api_version, self.session)
        while True:
            try:
                delivery = await self.db.claim_due()
                if delivery:
                    try:
                        publisher = telegram if delivery.platform == "telegram" else vk
                        external_id = await publisher.publish(delivery)
                        await self.db.delivery_succeeded(delivery.id, external_id)
                    except Exception as exc:
                        log.exception("Delivery %s failed", delivery.id)
                        await self.db.delivery_failed(delivery.id, str(exc), self.settings.max_delivery_attempts)
                    continue
                for notice in await self.db.terminal_notifications():
                    lines = [f"Публикация #{notice['id']}: {'завершена' if notice['status'] == 'sent' else 'завершена с ошибками' }."]
                    for item in notice["deliveries"]:
                        icon = "✅" if item["status"] == "sent" else "❌"
                        lines.append(f"{icon} {item['target_name']}" + (f": {item['last_error']}" if item["last_error"] else ""))
                    try:
                        await self.bot.send_message(notice["creator_id"], "\n".join(lines))
                        await self.db.mark_notified(notice["id"])
                        post = await self.db.post(notice["id"])
                        if post:
                            self._remove_media(post["media_paths"])
                    except Exception:
                        log.exception("Could not notify admin")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Scheduler loop failed")
            await asyncio.sleep(self.settings.scheduler_interval_seconds)

    @staticmethod
    def _remove_media(paths: list[str]) -> None:
        for path in paths:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                log.warning("Could not remove media file %s", path, exc_info=True)

    async def run(self) -> None:
        await self.db.initialize()
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))
        scheduler_task = asyncio.create_task(self.scheduler())
        try:
            await self.dp.start_polling(self.bot, allowed_updates=self.dp.resolve_used_update_types())
        finally:
            scheduler_task.cancel()
            await asyncio.gather(scheduler_task, return_exceptions=True)
            await self.session.close()
            await self.bot.session.close()
