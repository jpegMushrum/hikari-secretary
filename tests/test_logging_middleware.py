import asyncio
import unittest
from datetime import datetime, timezone

from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import Chat, Message, MessageEntity, Update, User

from app.logging_middleware import UpdateLoggingMiddleware


class UpdateLoggingMiddlewareTests(unittest.TestCase):
    @staticmethod
    def _update() -> Update:
        return Update(
            update_id=123,
            message=Message(
                message_id=10,
                date=datetime.now(timezone.utc),
                chat=Chat(id=20, type="private"),
                from_user=User(id=30, is_bot=False, first_name="Test"),
                text="Тест",
                entities=[MessageEntity(type="bold", offset=0, length=4)],
            ),
        )

    def test_unhandled_update_metadata_is_logged(self):
        async def handler(event, data):
            return UNHANDLED

        with self.assertLogs("app.logging_middleware", level="INFO") as captured:
            result = asyncio.run(
                UpdateLoggingMiddleware()(handler, self._update(), {})
            )

        self.assertIs(result, UNHANDLED)
        output = "\n".join(captured.output)
        self.assertIn("type=message", output)
        self.assertIn("content_type=text", output)
        self.assertIn("handled=False", output)
        self.assertIn("entities=['bold']", output)

    def test_exception_is_logged_and_reraised(self):
        async def handler(event, data):
            raise RuntimeError("failure")

        with self.assertLogs("app.logging_middleware", level="ERROR") as captured:
            with self.assertRaises(RuntimeError):
                asyncio.run(UpdateLoggingMiddleware()(handler, self._update(), {}))

        self.assertIn("Update failed: id=123", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
