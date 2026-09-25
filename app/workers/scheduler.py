from __future__ import annotations

import asyncio
import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from ..formatting import format_local
from ..keyboards import attendance_keyboard, registration_cancel_keyboard
from ..presentation import friendly_delivery_error, post_title, remove_media
from ..publishers import TelegramPublisher
from ..runtime import AppContext

log = logging.getLogger(__name__)


class SchedulerWorker:
    def __init__(self, context: AppContext):
        self.context = context
        self.publisher = TelegramPublisher(context.bot)

    async def run(self) -> None:
        while True:
            try:
                delivery = await self.context.db.claim_due()
                if delivery:
                    await self._deliver(delivery)
                    continue
                await self._send_due_reminders()
                await self._send_due_attendance_prompts()
                await self._send_terminal_notifications()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Scheduler loop failed")
            await asyncio.sleep(self.context.settings.scheduler_interval_seconds)

    async def _deliver(self, delivery) -> None:
        log.info(
            "Delivery claimed: delivery_id=%s post_id=%s target=%s attempt=%s",
            delivery.id, delivery.post_id, delivery.target_key, delivery.attempts + 1,
        )
        try:
            registration_url = None
            if delivery.event_enabled and self.context.bot_username:
                registration_url = (
                    f"https://t.me/{self.context.bot_username}?start=event_{delivery.post_id}"
                )
            external_id = await self.publisher.publish(delivery, registration_url)
            await self.context.db.delivery_succeeded(delivery.id, external_id)
            log.info(
                "Delivery succeeded: delivery_id=%s post_id=%s external_id=%s",
                delivery.id, delivery.post_id, external_id,
            )
            await self._notify_admin(
                delivery.creator_id,
                f"✅ Публикация #{delivery.post_id}: «{delivery.target_name}» — опубликовано.",
            )
        except Exception as exc:
            log.exception("Delivery %s failed", delivery.id)
            permanent = isinstance(exc, (TelegramBadRequest, TelegramForbiddenError))
            max_attempts = 1 if permanent else self.context.settings.max_delivery_attempts
            await self.context.db.delivery_failed(delivery.id, str(exc), max_attempts)
            attempt = delivery.attempts + 1
            reason = friendly_delivery_error(exc)
            if permanent or attempt >= self.context.settings.max_delivery_attempts:
                text = (
                    f"❌ Публикация #{delivery.post_id}: «{delivery.target_name}» — не опубликовано.\n"
                    f"Причина: {reason}"
                )
            else:
                text = (
                    f"⚠️ Публикация #{delivery.post_id}: «{delivery.target_name}» — попытка "
                    f"{attempt}/{self.context.settings.max_delivery_attempts} не удалась. "
                    f"Бот повторит отправку.\nПричина: {reason}"
                )
            await self._notify_admin(delivery.creator_id, text)

    async def _send_due_reminders(self) -> None:
        reminders = await self.context.db.due_reminders(
            self.context.settings.event_reminder_hours
        )
        if reminders:
            log.info("Due event reminders found: count=%s", len(reminders))
        for reminder in reminders:
            try:
                await self.context.bot.send_message(
                    reminder["user_id"],
                    f"Напоминание: скоро начнётся мероприятие «{post_title(reminder['text'])}».\n"
                    f"Начало: {format_local(reminder['starts_at'], self.context.settings.timezone)} "
                    f"({self.context.settings.timezone_name}).",
                    reply_markup=registration_cancel_keyboard(reminder["post_id"]),
                )
                await self.context.db.mark_reminder_sent(
                    reminder["user_id"], reminder["post_id"]
                )
                log.info(
                    "Event reminder sent: post_id=%s user_id=%s",
                    reminder["post_id"], reminder["user_id"],
                )
            except TelegramForbiddenError:
                log.warning(
                    "Event reminder skipped: reason=bot_blocked post_id=%s user_id=%s",
                    reminder["post_id"], reminder["user_id"],
                )
                await self.context.db.mark_reminder_sent(
                    reminder["user_id"], reminder["post_id"]
                )
            except Exception:
                log.exception("Could not send event reminder")

    async def _send_due_attendance_prompts(self) -> None:
        prompts = await self.context.db.due_attendance_prompts()
        if prompts:
            log.info("Due attendance prompts found: count=%s", len(prompts))
        for attendance in prompts:
            try:
                await self.context.bot.send_message(
                    attendance["user_id"],
                    f"Вы посетили мероприятие «{post_title(attendance['text'])}»?",
                    reply_markup=attendance_keyboard(attendance["post_id"]),
                )
                await self.context.db.mark_attendance_prompt_sent(
                    attendance["user_id"], attendance["post_id"]
                )
                log.info(
                    "Attendance prompt sent: post_id=%s user_id=%s",
                    attendance["post_id"], attendance["user_id"],
                )
            except TelegramForbiddenError:
                log.warning(
                    "Attendance prompt skipped: reason=bot_blocked post_id=%s user_id=%s",
                    attendance["post_id"], attendance["user_id"],
                )
                await self.context.db.mark_attendance_prompt_sent(
                    attendance["user_id"], attendance["post_id"]
                )
            except Exception:
                log.exception("Could not send attendance prompt")

    async def _send_terminal_notifications(self) -> None:
        for notice in await self.context.db.terminal_notifications():
            lines = [
                f"Публикация #{notice['id']}: "
                f"{'завершена' if notice['status'] == 'sent' else 'завершена с ошибками'}."
            ]
            for item in notice["deliveries"]:
                icon = "✅" if item["status"] == "sent" else "❌"
                lines.append(
                    f"{icon} {item['target_name']}"
                    + (f": {item['last_error']}" if item["last_error"] else "")
                )
            try:
                await self.context.bot.send_message(notice["creator_id"], "\n".join(lines))
                await self.context.db.mark_notified(notice["id"])
                post = await self.context.db.post(notice["id"])
                if post:
                    remove_media(post["media_paths"])
            except Exception:
                log.exception("Could not notify admin")

    async def _notify_admin(self, admin_id: int, text: str) -> None:
        try:
            await self.context.bot.send_message(admin_id, text)
        except Exception:
            log.exception("Could not send delivery status to admin %s", admin_id)
