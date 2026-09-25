import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

from app.handlers.publications import PublicationHandlers


class DraftDisplayTests(unittest.TestCase):
    @staticmethod
    def _handlers(post: dict):
        settings = SimpleNamespace(
            targets=(),
            timezone=ZoneInfo("Europe/Moscow"),
        )
        bot = Mock()
        bot.attach_mock(AsyncMock(), "send_rich_message")
        bot.attach_mock(AsyncMock(), "send_message")
        context = SimpleNamespace(
            db=SimpleNamespace(post=AsyncMock(return_value=post)),
            settings=settings,
            bot=bot,
        )
        return PublicationHandlers(context, None), bot

    def test_rich_message_is_echoed_before_settings(self):
        post = {
            "deliveries": [],
            "text": "Лекция\nこんにちは",
            "media_paths": [],
            "rich_message": {
                "blocks": [
                    {"type": "heading", "text": "Лекция", "size": 2},
                    {"type": "paragraph", "text": "こんにちは"},
                ]
            },
            "event": None,
        }
        handlers, bot = self._handlers(post)

        asyncio.run(handlers.show_draft(100, 11))

        self.assertEqual(
            [call[0] for call in bot.method_calls],
            ["send_rich_message", "send_message"],
        )
        settings_text = bot.send_message.await_args.args[1]
        self.assertTrue(settings_text.startswith("Настройки поста #11"))
        self.assertNotIn("こんにちは", settings_text)

    def test_regular_post_keeps_single_draft_message(self):
        post = {
            "deliveries": [],
            "text": "Обычный пост",
            "media_paths": [],
            "rich_message": None,
            "event": None,
        }
        handlers, bot = self._handlers(post)

        asyncio.run(handlers.show_draft(100, 12))

        bot.send_rich_message.assert_not_awaited()
        bot.send_message.assert_awaited_once()
        self.assertIn("Черновик #12\n\nОбычный пост", bot.send_message.await_args.args[1])

    def test_rich_settings_edit_does_not_repeat_preview(self):
        post = {
            "deliveries": [],
            "text": "Лекция",
            "media_paths": [],
            "rich_message": {
                "blocks": [{"type": "paragraph", "text": "Лекция"}]
            },
            "event": None,
        }
        handlers, bot = self._handlers(post)
        settings_message = SimpleNamespace(edit_text=AsyncMock())

        asyncio.run(handlers.show_draft(100, 13, settings_message))

        bot.send_rich_message.assert_not_awaited()
        bot.send_message.assert_not_awaited()
        settings_message.edit_text.assert_awaited_once()
        self.assertTrue(
            settings_message.edit_text.await_args.args[0].startswith(
                "Настройки поста #13"
            )
        )


if __name__ == "__main__":
    unittest.main()
