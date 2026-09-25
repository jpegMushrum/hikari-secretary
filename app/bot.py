from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, Router

from .access import AdminAccess
from .config import Settings
from .db import Database
from .handlers.core import CoreHandlers
from .handlers.inbox import InboxHandlers
from .handlers.publications import PublicationHandlers
from .handlers.registrations import RegistrationHandlers
from .logging_middleware import UpdateLoggingMiddleware
from .runtime import AppContext
from .workers.scheduler import SchedulerWorker

log = logging.getLogger(__name__)


class SecretaryBot:
    """Application composition root for the Telegram bot."""

    def __init__(self, settings: Settings):
        bot = Bot(settings.telegram_bot_token)
        database = Database(settings.database_path)
        self.context = AppContext(settings=settings, bot=bot, db=database)
        self.dispatcher = Dispatcher()
        self.router = Router()

        access = AdminAccess(self.context)
        registrations = RegistrationHandlers(self.context, access)
        publications = PublicationHandlers(self.context, access)
        core = CoreHandlers(self.context, access, registrations)
        inbox = InboxHandlers(registrations, publications)

        core.register(self.router)
        registrations.register(self.router)
        publications.register(self.router)
        # The catch-all content handler must be registered after specific commands.
        inbox.register(self.router)

        self.worker = SchedulerWorker(self.context)
        self.dispatcher.update.outer_middleware(UpdateLoggingMiddleware())
        self.dispatcher.include_router(self.router)

    @property
    def settings(self) -> Settings:
        return self.context.settings

    @property
    def bot(self) -> Bot:
        return self.context.bot

    @property
    def db(self) -> Database:
        return self.context.db

    async def run(self) -> None:
        log.info("Initializing database: path=%s", self.settings.database_path)
        await self.db.initialize()
        me = await self.bot.get_me()
        self.context.bot_username = me.username
        log.info(
            "Bot initialized: id=%s username=@%s targets=%s",
            me.id,
            me.username,
            len(self.settings.targets),
        )
        scheduler_task = asyncio.create_task(self.worker.run())
        try:
            await self.dispatcher.start_polling(
                self.bot,
                allowed_updates=self.dispatcher.resolve_used_update_types(),
            )
        finally:
            scheduler_task.cancel()
            await asyncio.gather(scheduler_task, return_exceptions=True)
            await self.bot.session.close()
