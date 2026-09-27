import asyncio
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import Database
from migrations.runner import (
    migration_001_baseline,
    migration_002_profile_v2,
    migration_003_events_and_registration_preferences,
    migrate,
)


async def migrated_database(path: Path) -> Database:
    migrate(path, create_backup=False)
    db = Database(path)
    await db.initialize()
    return db


class DatabaseTests(unittest.TestCase):
    def test_v4_adds_ai_infrastructure_to_v3_database(self):
        asyncio.run(self._v4_adds_ai_infrastructure_to_v3_database())

    async def _v4_adds_ai_infrastructure_to_v3_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """CREATE TABLE schema_migrations (
                        version INTEGER PRIMARY KEY,name TEXT NOT NULL,applied_at TEXT NOT NULL
                    )"""
                )
                migration_001_baseline(connection)
                migration_002_profile_v2(connection)
                migration_003_events_and_registration_preferences(connection)
                connection.execute(
                    """INSERT INTO posts(creator_id,text,created_at,status)
                       VALUES(1,'Существующий пост','now','sent')"""
                )
                connection.executemany(
                    "INSERT INTO schema_migrations(version,name,applied_at) VALUES(?,?,'now')",
                    [
                        (1, "baseline"),
                        (2, "profile_v2"),
                        (3, "events_and_registration_preferences"),
                    ],
                )
                connection.commit()
            finally:
                connection.close()

            self.assertEqual(migrate(path, create_backup=False), [4])
            db = Database(path)
            await db.initialize()
            post = await db.post(1)
            self.assertEqual(post["source"], "admin")
            async with db.connect() as connection:
                table = await (await connection.execute(
                    "SELECT name FROM sqlite_master WHERE name='ai_topic_jobs'"
                )).fetchone()
            self.assertIsNotNone(table)

    def test_v3_migration_backfills_event_title_and_preserves_registration(self):
        asyncio.run(self._v3_migration_backfills_event_title_and_preserves_registration())

    async def _v3_migration_backfills_event_title_and_preserves_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """CREATE TABLE schema_migrations (
                        version INTEGER PRIMARY KEY,name TEXT NOT NULL,applied_at TEXT NOT NULL
                    )"""
                )
                migration_001_baseline(connection)
                migration_002_profile_v2(connection)
                now = datetime.now(timezone.utc)
                connection.execute(
                    """INSERT INTO posts(id,creator_id,text,created_at,status)
                       VALUES(1,1,'Старое название','now','sent')"""
                )
                connection.execute(
                    """INSERT INTO events(post_id,starts_at,ends_at,created_at)
                       VALUES(1,?,?,?)""",
                    (
                        (now + timedelta(hours=2)).isoformat(),
                        (now + timedelta(hours=3)).isoformat(),
                        now.isoformat(),
                    ),
                )
                connection.execute(
                    """INSERT INTO user_profiles(
                        user_id,surname,given_name,full_name,created_at,updated_at
                    ) VALUES(5,'','','Пользователь','now','now')"""
                )
                connection.execute(
                    """INSERT INTO registrations(
                        post_id,user_id,reminders_enabled,status,registered_at
                    ) VALUES(1,5,1,'registered','now')"""
                )
                connection.executemany(
                    "INSERT INTO schema_migrations(version,name,applied_at) VALUES(?,?,'now')",
                    [(1, "baseline"), (2, "profile_v2")],
                )
                connection.commit()
            finally:
                connection.close()

            migrate(path, create_backup=False)
            db = Database(path)
            await db.initialize()
            post = await db.post(1)
            self.assertEqual(post["event"]["title"], "Старое название")
            registration = await db.registration(5, 1)
            self.assertEqual(registration["reminders_enabled"], 1)
            self.assertIsNone(registration["reminder_offset_minutes"])
            profile = await db.profile(5)
            self.assertIsNone(profile["is_russian_citizen"])
            self.assertIsNone(profile["is_itmo_student"])

    def test_existing_profiles_are_migrated_without_data_loss(self):
        asyncio.run(self._existing_profiles_are_migrated_without_data_loss())

    async def _existing_profiles_are_migrated_without_data_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """CREATE TABLE posts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        creator_id INTEGER NOT NULL,
                        text TEXT NOT NULL DEFAULT '',
                        entities_json TEXT NOT NULL DEFAULT '[]',
                        status TEXT NOT NULL DEFAULT 'draft',
                        scheduled_at TEXT,
                        created_at TEXT NOT NULL,
                        completed_at TEXT,
                        notified INTEGER NOT NULL DEFAULT 0
                    )"""
                )
                connection.execute(
                    """CREATE TABLE user_profiles (
                        user_id INTEGER PRIMARY KEY,
                        surname TEXT NOT NULL,
                        given_name TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )"""
                )
                connection.execute(
                    """INSERT INTO user_profiles(
                        user_id,surname,given_name,created_at,updated_at
                    ) VALUES(1,'Иванов','Иван','now','now')"""
                )
                connection.commit()
            finally:
                connection.close()

            db = await migrated_database(path)
            async with db.connect() as connection:
                columns = {
                    row["name"]
                    for row in await (
                        await connection.execute("PRAGMA table_info(posts)")
                    ).fetchall()
                }
            self.assertIn("rich_message_json", columns)
            profile = await db.profile(1)
            self.assertEqual(profile["full_name"], "Иван Иванов")

    def test_delivery_lifecycle(self):
        asyncio.run(self._delivery_lifecycle())

    async def _delivery_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            db = await migrated_database(Path(directory) / "test.sqlite3")
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

    def test_event_pages_are_bounded_and_stably_ordered(self):
        asyncio.run(self._event_pages_are_bounded_and_stably_ordered())

    async def _event_pages_are_bounded_and_stably_ordered(self):
        with tempfile.TemporaryDirectory() as directory:
            db = await migrated_database(Path(directory) / "test.sqlite3")
            now = datetime.now(timezone.utc)
            created: list[int] = []
            for index in range(7):
                post_id = await db.create_post(1, f"Пост {index}", [], [])
                created.append(post_id)
                await db.toggle_delivery(post_id, "channel", "Канал", "-100")
                start = now + timedelta(days=index + 1)
                await db.set_event(
                    post_id, f"Мероприятие {index}", start, start + timedelta(hours=1)
                )
                await db.schedule(post_id, now)
                delivery = await db.claim_due()
                await db.delivery_succeeded(delivery.id, str(index))

            first = await db.available_events_page(99, 0, page_size=5)
            second = await db.available_events_page(99, 1, page_size=5)
            self.assertEqual(first.total, 7)
            self.assertEqual(first.pages, 2)
            self.assertEqual(len(first.items), 5)
            self.assertEqual(len(second.items), 2)
            self.assertEqual(
                [row["post_id"] for row in first.items + second.items], created
            )

    def test_event_registration_lifecycle(self):
        asyncio.run(self._event_registration_lifecycle())

    def test_rich_message_is_preserved_for_delivery(self):
        asyncio.run(self._rich_message_is_preserved_for_delivery())

    async def _rich_message_is_preserved_for_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            db = await migrated_database(Path(directory) / "test.sqlite3")
            rich_message = {
                "blocks": [
                    {"type": "heading", "text": "Лекция", "size": 2},
                    {"type": "paragraph", "text": "こんにちは"},
                ]
            }
            post_id = await db.create_post(
                100, "Лекция\nこんにちは", [], [], rich_message
            )
            post = await db.post(post_id)
            self.assertEqual(post["rich_message"], rich_message)

            await db.toggle_delivery(post_id, "channel", "Канал", "-100123")
            await db.schedule(post_id, datetime.now(timezone.utc))
            delivery = await db.claim_due()
            self.assertEqual(delivery.rich_message, rich_message)

    async def _event_registration_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            db = await migrated_database(Path(directory) / "test.sqlite3")
            post_id = await db.create_post(100, "Японский разговорный клуб", [], [])
            await db.toggle_delivery(post_id, "channel", "Канал", "-100123")
            starts_at = datetime.now(timezone.utc) + timedelta(hours=12)
            ends_at = starts_at + timedelta(hours=2)
            self.assertTrue(await db.set_event(
                post_id, "Японский разговорный клуб", starts_at, ends_at
            ))
            self.assertTrue(await db.schedule(post_id, datetime.now(timezone.utc)))
            delivery = await db.claim_due()
            self.assertTrue(delivery.event_enabled)
            await db.delivery_succeeded(delivery.id, "10")
            available = await db.available_events(200)
            self.assertEqual([row["post_id"] for row in available], [post_id])

            await db.begin_registration_flow(200, post_id, "full_name")
            await db.save_profile(200, "Иван Иванов", "ivan", "Ваня", None)
            await db.update_profile_answers(
                200, is_russian_citizen=True, is_itmo_student=False
            )
            await db.update_registration_flow(200, "reminder")
            self.assertTrue(await db.register(200, post_id, 120))
            await db.delete_registration_flow(200)
            self.assertEqual(await db.available_events(200), [])

            registrations = await db.user_registrations(200)
            self.assertEqual(len(registrations), 1)
            self.assertEqual(await db.due_reminders(), [])
            async with db.connect() as connection:
                await connection.execute(
                    "UPDATE events SET starts_at=? WHERE post_id=?",
                    ((datetime.now(timezone.utc) + timedelta(minutes=90)).isoformat(), post_id),
                )
                await connection.commit()
            due = await db.due_reminders()
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["reminder_offset_minutes"], 120)
            await db.mark_reminder_sent(200, post_id)
            self.assertEqual(await db.due_reminders(), [])

            await db.begin_profile_edit(200)
            edit_flow = await db.profile_edit_flow(200)
            self.assertEqual(edit_flow["stage"], "full_name")
            await db.save_profile(200, "Иван Петров", None, "Пирожок", None)
            await db.delete_profile_edit(200)
            self.assertIsNone(await db.profile_edit_flow(200))

            participants = await db.event_registrations(post_id)
            self.assertEqual(participants[0]["full_name"], "Иван Петров")
            self.assertEqual(participants[0]["telegram_first_name"], "Пирожок")
            self.assertEqual(participants[0]["is_russian_citizen"], 1)
            self.assertEqual(participants[0]["is_itmo_student"], 0)
            self.assertTrue(await db.cancel_registration(200, post_id))
            self.assertEqual(await db.user_registrations(200), [])
            available = await db.available_events(200)
            self.assertEqual([row["post_id"] for row in available], [post_id])
            participants = await db.event_registrations(post_id)
            self.assertEqual(participants[0]["status"], "cancelled")

    def test_attendance_is_requested_only_for_active_registration(self):
        asyncio.run(self._attendance_is_requested_only_for_active_registration())

    async def _attendance_is_requested_only_for_active_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            db = await migrated_database(Path(directory) / "test.sqlite3")
            post_id = await db.create_post(100, "Встреча", [], [])
            await db.toggle_delivery(post_id, "channel", "Канал", "-100123")
            starts_at = datetime.now(timezone.utc) + timedelta(minutes=10)
            ends_at = starts_at + timedelta(hours=1)
            await db.set_event(post_id, "Встреча", starts_at, ends_at)
            await db.schedule(post_id, datetime.now(timezone.utc))
            delivery = await db.claim_due()
            await db.delivery_succeeded(delivery.id, "11")
            await db.save_profile(201, "Анна Петрова", "anna", "Анна", "Петрова")
            await db.update_profile_answers(
                201, is_russian_citizen=False, is_itmo_student=True
            )
            self.assertTrue(await db.register(201, post_id, None))

            async with db.connect() as connection:
                await connection.execute(
                    "UPDATE events SET ends_at=? WHERE post_id=?",
                    ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), post_id),
                )
                await connection.commit()

            prompts = await db.due_attendance_prompts()
            self.assertEqual(len(prompts), 1)
            self.assertEqual(len(await db.admin_events(past=True)), 1)
            self.assertEqual(await db.admin_events(), [])
            await db.mark_attendance_prompt_sent(201, post_id)
            self.assertTrue(await db.record_attendance(201, post_id, True))
            participants = await db.event_registrations(post_id)
            self.assertEqual(participants[0]["attended"], 1)

    def test_cancelled_event_stops_notifications(self):
        asyncio.run(self._cancelled_event_stops_notifications())

    async def _cancelled_event_stops_notifications(self):
        with tempfile.TemporaryDirectory() as directory:
            db = await migrated_database(Path(directory) / "test.sqlite3")
            post_id = await db.create_post(100, "Отменяемая встреча", [], [])
            await db.toggle_delivery(post_id, "channel", "Канал", "-100123")
            starts_at = datetime.now(timezone.utc) + timedelta(hours=2)
            await db.set_event(
                post_id, "Отменяемая встреча",
                starts_at, starts_at + timedelta(hours=1)
            )
            await db.schedule(post_id, datetime.now(timezone.utc))
            delivery = await db.claim_due()
            await db.delivery_succeeded(delivery.id, "12")
            await db.save_profile(202, "Пётр Сидоров", None, "Пётр", "Сидоров")
            await db.update_profile_answers(
                202, is_russian_citizen=True, is_itmo_student=True
            )
            await db.register(202, post_id, 60)
            self.assertEqual(len(await db.admin_events()), 1)

            participants = await db.cancel_event(post_id)
            self.assertEqual(participants[0]["user_id"], 202)
            self.assertEqual(await db.due_reminders(), [])
            self.assertEqual(await db.user_registrations(202), [])
            self.assertEqual(await db.admin_events(), [])
            self.assertEqual(await db.admin_events(past=True), [])
            self.assertIsNone(await db.cancel_event(post_id))


if __name__ == "__main__":
    unittest.main()
