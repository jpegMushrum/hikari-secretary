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
            rich_message=None,
            media_paths=[],
            attempts=0,
        )
        result = await TelegramPublisher(bot).publish(delivery)
        self.assertEqual(result, "77")
        bot.send_message.assert_awaited_once_with(
            -100123, "Тест", entities=None, message_thread_id=42
        )

    def test_registration_link_is_appended_to_regular_text(self):
        asyncio.run(self._registration_link_is_appended_to_regular_text())

    async def _registration_link_is_appended_to_regular_text(self):
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
            rich_message=None,
            media_paths=[],
            attempts=0,
            event_enabled=True,
        )
        url = "https://t.me/example_bot?start=event_2"
        await TelegramPublisher(bot).publish(delivery, url)
        call = bot.send_message.await_args
        self.assertEqual(call.args[1], f"Мероприятие\n\nРегистрация: {url}")
        self.assertNotIn("reply_markup", call.kwargs)

    def test_rich_message_is_sent_with_registration_link(self):
        asyncio.run(self._rich_message_is_sent_with_registration_link())

    def test_registration_link_is_appended_to_photo_caption(self):
        asyncio.run(self._registration_link_is_appended_to_photo_caption())

    async def _registration_link_is_appended_to_photo_caption(self):
        bot = SimpleNamespace(
            send_photo=AsyncMock(return_value=SimpleNamespace(message_id=80))
        )
        delivery = Delivery(
            id=1,
            post_id=2,
            creator_id=3,
            target_key="channel",
            target_name="Канал",
            destination="-100123",
            message_thread_id=None,
            text="Мероприятие",
            entities=[],
            rich_message=None,
            media_paths=["photo.jpg"],
            attempts=0,
            event_enabled=True,
        )
        url = "https://t.me/example_bot?start=event_2"

        await TelegramPublisher(bot).publish(delivery, url)

        call = bot.send_photo.await_args
        self.assertEqual(call.kwargs["caption"], f"Мероприятие\n\nРегистрация: {url}")
        self.assertNotIn("reply_markup", call.kwargs)

    async def _rich_message_is_sent_with_registration_link(self):
        bot = SimpleNamespace(
            send_rich_message=AsyncMock(return_value=SimpleNamespace(message_id=79))
        )
        delivery = Delivery(
            id=1,
            post_id=2,
            creator_id=3,
            target_key="chat",
            target_name="Чат",
            destination="-100123",
            message_thread_id=42,
            text="Лекция\nこんにちは",
            entities=[],
            rich_message={
                "blocks": [
                    {
                        "type": "heading",
                        "text": {"type": "bold", "text": "Лекция"},
                        "size": 2,
                    },
                    {"type": "paragraph", "text": "こんにちは"},
                ]
            },
            media_paths=[],
            attempts=0,
            event_enabled=True,
        )
        url = "https://t.me/example_bot?start=event_2"
        result = await TelegramPublisher(bot).publish(delivery, url)
        self.assertEqual(result, "79")
        call = bot.send_rich_message.await_args
        self.assertEqual(call.args[0], -100123)
        self.assertEqual(call.args[1].blocks[0].type, "heading")
        registration_block = call.args[1].blocks[-1]
        self.assertEqual(registration_block.type, "buttons")
        self.assertEqual(registration_block.buttons[0].url, url)
        self.assertEqual(registration_block.buttons[0].text, "Зарегистрироваться")
        self.assertEqual(call.kwargs["message_thread_id"], 42)
        self.assertNotIn("reply_markup", call.kwargs)


if __name__ == "__main__":
    unittest.main()
