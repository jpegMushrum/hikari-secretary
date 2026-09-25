from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from .publications import PublicationHandlers
from .registrations import RegistrationHandlers


class InboxHandlers:
    """Routes catch-all message input without coupling business domains."""

    def __init__(
        self,
        registrations: RegistrationHandlers,
        publications: PublicationHandlers,
    ):
        self.registrations = registrations
        self.publications = publications

    def register(self, router: Router) -> None:
        router.message.register(
            self.content, F.content_type.in_({"text", "photo", "rich_message"})
        )

    async def content(self, message: Message) -> None:
        if await self.registrations.handle_text_flow(message):
            return
        await self.publications.content(message)

