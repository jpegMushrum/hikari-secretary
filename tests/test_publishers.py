import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.db import Delivery
from app.bot import SecretaryBot
from app.publishers import TelegramPublisher


class TelegramPublisherTests(unittest.TestCase):
    def test_closed_topic_error_is_human_readable(self):
        message = SecretaryBot._friendly_delivery_error(Exception("Bad Request: TOPIC_CLOSED"))
        self.assertIn("топик Telegram закрыт", message)

    def test_text_is_sent_to_requested_topic(self):
        asyncio.run(self._text_is_sent_to_requested_topic())

    async def _text_is_sent_to_requested_topic(self):
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=77)))
        delivery = Delivery(
            id=1,
            post_id=2,
            creator_id=3,
            target_key="topic",
            target_name="Топик",
            destination="-100123",
            message_thread_id=42,
            text="Тест",
            entities=[],
            media_paths=[],
            attempts=0,
        )
        result = await TelegramPublisher(bot).publish(delivery)
        self.assertEqual(result, "77")
        bot.send_message.assert_awaited_once_with(
            -100123, "Тест", entities=None, message_thread_id=42, reply_markup=None
        )

    def test_registration_link_is_attached(self):
        asyncio.run(self._registration_link_is_attached())

    async def _registration_link_is_attached(self):
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=78)))
        delivery = Delivery(
            id=1,
            post_id=2,
            creator_id=3,
            target_key="chat",
            target_name="Чат",
            destination="-100123",
            message_thread_id=None,
            text="Мероприятие",
            entities=[],
            media_paths=[],
            attempts=0,
            event_enabled=True,
        )
        url = "https://t.me/example_bot?start=event_2"
        await TelegramPublisher(bot).publish(delivery, url)
        markup = bot.send_message.await_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].url, url)


if __name__ == "__main__":
    unittest.main()
