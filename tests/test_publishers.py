import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.db import Delivery
from app.publishers import TelegramPublisher


class TelegramPublisherTests(unittest.TestCase):
    def test_text_is_sent_to_requested_topic(self):
        asyncio.run(self._text_is_sent_to_requested_topic())

    async def _text_is_sent_to_requested_topic(self):
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=77)))
        delivery = Delivery(
            id=1,
            post_id=2,
            creator_id=3,
            platform="telegram",
            target_key="topic",
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
            -100123, "Тест", entities=None, message_thread_id=42
        )


if __name__ == "__main__":
    unittest.main()
