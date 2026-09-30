from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    MenuButtonCommands,
)

from .access import AdminAccess
from .config import Settings
from .db import Database
from .handlers.core import CoreHandlers
from .handlers.ai_topics import AiTopicHandlers
from .handlers.inbox import InboxHandlers
from .handlers.publications import PublicationHandlers
from .handlers.registrations import RegistrationHandlers
from .logging_middleware import UpdateLoggingMiddleware
from .runtime import AppContext
from .services.publications import PublicationService
from .services.daily_topics import DailyTopicService
from .repositories.daily_topics import DailyTopicRepository
from .integrations.deepseek import DeepSeekTopicProvider
from .workers.scheduler import SchedulerWorker
from .workers.base import BackgroundWorker
from .workers.daily_topics import DailyTopicPlannerWorker, DailyTopicWorker

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
        publication_service = PublicationService(database, settings.targets)
        topic_repository = DailyTopicRepository(database)
        topic_service: DailyTopicService | None = None
        if settings.deepseek_api_key and settings.ai_topics.target:
            topic_service = DailyTopicService(
                DeepSeekTopicProvider.from_settings(settings),
                publication_service,
                settings.ai_topics.target.key,
            )
        registrations = RegistrationHandlers(self.context, access)
        publications = PublicationHandlers(
            self.context, access, publication_service
        )
        core = CoreHandlers(self.context, access, registrations)
        ai_topics = AiTopicHandlers(
            self.context, access, topic_service, topic_repository
        )
        inbox = InboxHandlers(registrations, publications, ai_topics)

        core.register(self.router)
        registrations.register(self.router)
        publications.register(self.router)
        ai_topics.register(self.router)
        # The catch-all content handler must be registered after specific commands.
        inbox.register(self.router)

        workers: list[BackgroundWorker] = [SchedulerWorker(self.context)]
        if topic_service and settings.ai_topics.auto_publish_time:
            workers.extend((
                DailyTopicPlannerWorker(
                    topic_repository,
                    publish_time=settings.ai_topics.auto_publish_time,
                    timezone_value=settings.timezone,
                ),
                DailyTopicWorker(
                    topic_repository,
                    topic_service,
                    creator_id=min(settings.admin_ids),
                    bot=bot,
                    admin_ids=settings.admin_ids,
                    timezone_value=settings.timezone,
                ),
            ))
        self.workers = tuple(workers)
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
        await self._configure_telegram_menu()
        log.info(
            "Bot initialized: id=%s username=@%s targets=%s",
            me.id,
            me.username,
            len(self.settings.targets),
        )
        worker_tasks = [
            asyncio.create_task(worker.run(), name=f"worker:{worker.name}")
            for worker in self.workers
        ]
        try:
            await self.dispatcher.start_polling(
                self.bot,
                allowed_updates=self.dispatcher.resolve_used_update_types(),
            )
        finally:
            for task in worker_tasks:
                task.cancel()
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            await self.bot.session.close()

    async def _configure_telegram_menu(self) -> None:
        user_commands = [
            BotCommand(command="start", description="Открыть главное меню"),
            BotCommand(command="events", description="Мои мероприятия"),
            BotCommand(command="profile", description="Настройка профиля"),
        ]
        admin_commands = [
            BotCommand(command="start", description="Открыть панель администратора"),
            BotCommand(command="queue", description="Очередь публикаций"),
            BotCommand(command="registrations", description="Мероприятия и участники"),
            BotCommand(command="events", description="Мои мероприятия"),
            BotCommand(command="profile", description="Настройка профиля"),
            BotCommand(command="help", description="Помощь"),
        ]
        await self.bot.set_my_commands(
            user_commands, scope=BotCommandScopeAllPrivateChats()
        )
        await self.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        for admin_id in self.settings.admin_ids:
            try:
                await self.bot.set_my_commands(
                    admin_commands, scope=BotCommandScopeChat(chat_id=admin_id)
                )
            except TelegramBadRequest:
                log.warning(
                    "Could not configure command menu for admin_id=%s; "
                    "the administrator may need to start the bot first",
                    admin_id,
                )
