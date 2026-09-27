import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.inbox import InboxHandlers


class InboxHandlersTests(unittest.TestCase):
    def test_active_registration_flow_stops_publication_handling(self) -> None:
        registrations = SimpleNamespace(handle_text_flow=AsyncMock(return_value=True))
        publications = SimpleNamespace(content=AsyncMock())
        ai_topics = SimpleNamespace(handle_text_flow=AsyncMock(return_value=False))
        handlers = InboxHandlers(registrations, publications, ai_topics)
        message = SimpleNamespace()

        asyncio.run(handlers.content(message))

        registrations.handle_text_flow.assert_awaited_once_with(message)
        publications.content.assert_not_awaited()

    def test_message_without_registration_flow_reaches_publications(self) -> None:
        registrations = SimpleNamespace(handle_text_flow=AsyncMock(return_value=False))
        publications = SimpleNamespace(content=AsyncMock())
        ai_topics = SimpleNamespace(handle_text_flow=AsyncMock(return_value=False))
        handlers = InboxHandlers(registrations, publications, ai_topics)
        message = SimpleNamespace()

        asyncio.run(handlers.content(message))

        registrations.handle_text_flow.assert_awaited_once_with(message)
        publications.content.assert_awaited_once_with(message)

    def test_ai_comment_flow_stops_publication_handling(self) -> None:
        registrations = SimpleNamespace(handle_text_flow=AsyncMock(return_value=False))
        publications = SimpleNamespace(content=AsyncMock())
        ai_topics = SimpleNamespace(handle_text_flow=AsyncMock(return_value=True))
        handlers = InboxHandlers(registrations, publications, ai_topics)
        message = SimpleNamespace()

        asyncio.run(handlers.content(message))

        ai_topics.handle_text_flow.assert_awaited_once_with(message)
        publications.content.assert_not_awaited()

