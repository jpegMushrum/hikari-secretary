import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.db import Database


class DatabaseTests(unittest.TestCase):
    def test_delivery_lifecycle(self):
        asyncio.run(self._delivery_lifecycle())

    async def _delivery_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            await db.initialize()
            post_id = await db.create_post(100, "Тест", [], [])
            await db.toggle_delivery(post_id, "channel", "Канал", "-100123", 42)
            scheduled = await db.schedule(post_id, datetime.now(timezone.utc))
            self.assertTrue(scheduled)

            delivery = await db.claim_due()
            self.assertIsNotNone(delivery)
            self.assertEqual(delivery.text, "Тест")
            self.assertEqual(delivery.message_thread_id, 42)
            await db.delivery_succeeded(delivery.id, "42")

            post = await db.post(post_id)
            self.assertEqual(post["status"], "sent")
            notifications = await db.terminal_notifications()
            self.assertEqual(len(notifications), 1)
            self.assertEqual(notifications[0]["deliveries"][0]["status"], "sent")
            await db.mark_notified(post_id)
            self.assertEqual(await db.terminal_notifications(), [])


if __name__ == "__main__":
    unittest.main()
