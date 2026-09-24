from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Delivery:
    id: int
    post_id: int
    creator_id: int
    target_key: str
    target_name: str
    destination: str
    message_thread_id: int | None
    text: str
    entities: list[dict]
    rich_message: dict | None
    media_paths: list[str]
    attempts: int
    event_enabled: bool = False


class Database:
    def __init__(self, path: Path):
        self.path = path

    @asynccontextmanager
    async def connect(self):
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        try:
            yield db
        finally:
            await db.close()

    async def initialize(self) -> None:
        async with self.connect() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creator_id INTEGER NOT NULL,
                    text TEXT NOT NULL DEFAULT '',
                    entities_json TEXT NOT NULL DEFAULT '[]',
                    rich_message_json TEXT,
                    status TEXT NOT NULL DEFAULT 'draft',
                    scheduled_at TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    notified INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    path TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                    platform TEXT NOT NULL,
                    target_key TEXT NOT NULL,
                    target_name TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    message_thread_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    external_id TEXT,
                    last_error TEXT,
                    published_at TEXT,
                    UNIQUE(post_id, target_key)
                );
                CREATE INDEX IF NOT EXISTS idx_delivery_due
                ON deliveries(status, next_attempt_at);
                CREATE TABLE IF NOT EXISTS events (
                    post_id INTEGER PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
                    starts_at TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    cancelled_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id INTEGER PRIMARY KEY,
                    surname TEXT NOT NULL,
                    given_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS registration_flows (
                    user_id INTEGER PRIMARY KEY,
                    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                    stage TEXT NOT NULL,
                    surname TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profile_edit_flows (
                    user_id INTEGER PRIMARY KEY,
                    stage TEXT NOT NULL,
                    surname TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS registrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES user_profiles(user_id),
                    reminders_enabled INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'registered',
                    registered_at TEXT NOT NULL,
                    cancelled_at TEXT,
                    reminder_sent_at TEXT,
                    attendance_prompt_sent_at TEXT,
                    attended INTEGER,
                    attendance_recorded_at TEXT,
                    UNIQUE(post_id, user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_registrations_user
                ON registrations(user_id, status);
                """
            )
            columns = {
                row["name"]
                for row in await (await db.execute("PRAGMA table_info(deliveries)")).fetchall()
            }
            if "message_thread_id" not in columns:
                await db.execute("ALTER TABLE deliveries ADD COLUMN message_thread_id INTEGER")
            post_columns = {
                row["name"]
                for row in await (await db.execute("PRAGMA table_info(posts)")).fetchall()
            }
            if "rich_message_json" not in post_columns:
                await db.execute("ALTER TABLE posts ADD COLUMN rich_message_json TEXT")
            event_columns = {
                row["name"]
                for row in await (await db.execute("PRAGMA table_info(events)")).fetchall()
            }
            if "status" not in event_columns:
                await db.execute(
                    "ALTER TABLE events ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
                )
            if "cancelled_at" not in event_columns:
                await db.execute("ALTER TABLE events ADD COLUMN cancelled_at TEXT")
            await db.execute(
                "UPDATE deliveries SET status='retry', next_attempt_at=? WHERE status='publishing'",
                (utc_now().isoformat(),),
            )
            await db.execute(
                """UPDATE deliveries
                   SET status='failed', next_attempt_at=NULL,
                       last_error='Платформа больше не поддерживается'
                   WHERE platform<>'telegram' AND status IN ('pending','retry','publishing')"""
            )
            await db.execute(
                """UPDATE posts SET status='failed', completed_at=?
                   WHERE status='scheduled'
                     AND EXISTS (SELECT 1 FROM deliveries d WHERE d.post_id=posts.id)
                     AND NOT EXISTS (
                         SELECT 1 FROM deliveries d
                         WHERE d.post_id=posts.id AND d.status NOT IN ('sent','failed')
                     )""",
                (utc_now().isoformat(),),
            )
            await db.commit()

    async def create_post(
        self,
        creator_id: int,
        text: str,
        entities: list[dict],
        media_paths: list[str],
        rich_message: dict | None = None,
    ) -> int:
        async with self.connect() as db:
            cursor = await db.execute(
                """INSERT INTO posts(
                       creator_id,text,entities_json,rich_message_json,created_at
                   ) VALUES(?,?,?,?,?)""",
                (
                    creator_id,
                    text,
                    json.dumps(entities, ensure_ascii=False),
                    json.dumps(rich_message, ensure_ascii=False) if rich_message else None,
                    utc_now().isoformat(),
                ),
            )
            post_id = int(cursor.lastrowid)
            await db.executemany(
                "INSERT INTO media(post_id,position,path) VALUES(?,?,?)",
                [(post_id, index, path) for index, path in enumerate(media_paths)],
            )
            await db.commit()
            return post_id

    async def post(self, post_id: int):
        async with self.connect() as db:
            post = await (await db.execute("SELECT * FROM posts WHERE id=?", (post_id,))).fetchone()
            if not post:
                return None
            media = await (await db.execute("SELECT path FROM media WHERE post_id=? ORDER BY position", (post_id,))).fetchall()
            deliveries = await (await db.execute("SELECT * FROM deliveries WHERE post_id=? ORDER BY id", (post_id,))).fetchall()
            event = await (await db.execute("SELECT * FROM events WHERE post_id=?", (post_id,))).fetchone()
            return dict(post) | {
                "entities": json.loads(post["entities_json"]),
                "rich_message": (
                    json.loads(post["rich_message_json"])
                    if post["rich_message_json"] else None
                ),
                "media_paths": [row["path"] for row in media],
                "deliveries": [dict(row) for row in deliveries],
                "event": dict(event) if event else None,
            }

    async def set_event(self, post_id: int, starts_at: datetime, ends_at: datetime) -> bool:
        if ends_at <= starts_at:
            return False
        async with self.connect() as db:
            post = await (await db.execute(
                "SELECT status FROM posts WHERE id=?", (post_id,)
            )).fetchone()
            if not post or post["status"] != "draft":
                return False
            await db.execute(
                """INSERT INTO events(post_id,starts_at,ends_at,created_at) VALUES(?,?,?,?)
                   ON CONFLICT(post_id) DO UPDATE SET
                       starts_at=excluded.starts_at, ends_at=excluded.ends_at,
                       status='active', cancelled_at=NULL""",
                (
                    post_id,
                    starts_at.astimezone(timezone.utc).isoformat(),
                    ends_at.astimezone(timezone.utc).isoformat(),
                    utc_now().isoformat(),
                ),
            )
            await db.commit()
            return True

    async def remove_event(self, post_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                """DELETE FROM events WHERE post_id=?
                   AND EXISTS (SELECT 1 FROM posts WHERE id=? AND status='draft')""",
                (post_id, post_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def toggle_delivery(
        self,
        post_id: int,
        target_key: str,
        target_name: str,
        destination: str,
        message_thread_id: int | None = None,
    ) -> None:
        async with self.connect() as db:
            found = await (await db.execute(
                "SELECT id FROM deliveries WHERE post_id=? AND target_key=?", (post_id, target_key)
            )).fetchone()
            if found:
                await db.execute("DELETE FROM deliveries WHERE id=?", (found["id"],))
            else:
                await db.execute(
                    """INSERT INTO deliveries(
                           post_id,platform,target_key,target_name,destination,message_thread_id
                       ) VALUES(?,?,?,?,?,?)""",
                    (post_id, "telegram", target_key, target_name, destination, message_thread_id),
                )
            await db.commit()

    async def schedule(self, post_id: int, when: datetime) -> bool:
        async with self.connect() as db:
            count = await (await db.execute(
                "SELECT COUNT(*) AS n FROM deliveries WHERE post_id=? AND platform='telegram'",
                (post_id,),
            )).fetchone()
            if not count or count["n"] == 0:
                return False
            cursor = await db.execute(
                "UPDATE posts SET status='scheduled', scheduled_at=? WHERE id=? AND status='draft'",
                (when.astimezone(timezone.utc).isoformat(), post_id),
            )
            await db.execute(
                "UPDATE deliveries SET next_attempt_at=? WHERE post_id=? AND platform='telegram'",
                (when.astimezone(timezone.utc).isoformat(), post_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def cancel(self, post_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE posts SET status='cancelled', completed_at=? WHERE id=? AND status IN ('draft','scheduled')",
                (utc_now().isoformat(), post_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def queue(self, limit: int = 20) -> list[dict]:
        async with self.connect() as db:
            rows = await (await db.execute(
                """SELECT p.id,p.creator_id,p.scheduled_at,p.status,
                          GROUP_CONCAT(d.target_name, ', ') AS targets
                   FROM posts p JOIN deliveries d ON d.post_id=p.id
                   WHERE p.status='scheduled'
                   GROUP BY p.id ORDER BY p.scheduled_at LIMIT ?""",
                (limit,),
            )).fetchall()
            return [dict(row) for row in rows]

    async def claim_due(self) -> Delivery | None:
        now = utc_now().isoformat()
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute(
                """SELECT d.id,d.post_id,d.target_key,d.target_name,d.destination,
                          d.message_thread_id,d.attempts,
                          p.creator_id,p.text,p.entities_json,p.rich_message_json,
                          EXISTS(SELECT 1 FROM events e WHERE e.post_id=p.id) AS event_enabled
                   FROM deliveries d JOIN posts p ON p.id=d.post_id
                   WHERE p.status='scheduled' AND d.status IN ('pending','retry')
                     AND d.platform='telegram'
                     AND p.scheduled_at<=? AND d.next_attempt_at<=?
                   ORDER BY d.next_attempt_at,d.id LIMIT 1""",
                (now, now),
            )).fetchone()
            if not row:
                await db.commit()
                return None
            cursor = await db.execute(
                "UPDATE deliveries SET status='publishing' WHERE id=? AND status IN ('pending','retry')",
                (row["id"],),
            )
            if cursor.rowcount != 1:
                await db.rollback()
                return None
            media = await (await db.execute(
                "SELECT path FROM media WHERE post_id=? ORDER BY position", (row["post_id"],)
            )).fetchall()
            await db.commit()
            return Delivery(
                id=row["id"], post_id=row["post_id"], creator_id=row["creator_id"],
                target_key=row["target_key"], target_name=row["target_name"],
                destination=row["destination"],
                message_thread_id=row["message_thread_id"],
                text=row["text"], entities=json.loads(row["entities_json"]),
                rich_message=(
                    json.loads(row["rich_message_json"])
                    if row["rich_message_json"] else None
                ),
                media_paths=[item["path"] for item in media], attempts=row["attempts"],
                event_enabled=bool(row["event_enabled"]),
            )

    async def profile(self, user_id: int) -> dict | None:
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT * FROM user_profiles WHERE user_id=?", (user_id,)
            )).fetchone()
            return dict(row) if row else None

    async def save_profile(self, user_id: int, surname: str, given_name: str) -> None:
        now = utc_now().isoformat()
        async with self.connect() as db:
            await db.execute(
                """INSERT INTO user_profiles(user_id,surname,given_name,created_at,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       surname=excluded.surname, given_name=excluded.given_name,
                       updated_at=excluded.updated_at""",
                (user_id, surname, given_name, now, now),
            )
            await db.commit()

    async def begin_profile_edit(self, user_id: int) -> None:
        async with self.connect() as db:
            await db.execute(
                """INSERT INTO profile_edit_flows(user_id,stage,updated_at)
                   VALUES(?,'surname',?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       stage='surname',surname=NULL,updated_at=excluded.updated_at""",
                (user_id, utc_now().isoformat()),
            )
            await db.commit()

    async def profile_edit_flow(self, user_id: int) -> dict | None:
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT * FROM profile_edit_flows WHERE user_id=?", (user_id,)
            )).fetchone()
            return dict(row) if row else None

    async def update_profile_edit(
        self, user_id: int, stage: str, surname: str | None = None
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                """UPDATE profile_edit_flows
                   SET stage=?,surname=COALESCE(?,surname),updated_at=?
                   WHERE user_id=?""",
                (stage, surname, utc_now().isoformat(), user_id),
            )
            await db.commit()

    async def delete_profile_edit(self, user_id: int) -> None:
        async with self.connect() as db:
            await db.execute("DELETE FROM profile_edit_flows WHERE user_id=?", (user_id,))
            await db.commit()

    async def begin_registration_flow(self, user_id: int, post_id: int, stage: str) -> None:
        async with self.connect() as db:
            await db.execute(
                """INSERT INTO registration_flows(user_id,post_id,stage,updated_at)
                   VALUES(?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       post_id=excluded.post_id, stage=excluded.stage,
                       surname=NULL, updated_at=excluded.updated_at""",
                (user_id, post_id, stage, utc_now().isoformat()),
            )
            await db.commit()

    async def registration_flow(self, user_id: int) -> dict | None:
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT * FROM registration_flows WHERE user_id=?", (user_id,)
            )).fetchone()
            return dict(row) if row else None

    async def update_registration_flow(
        self, user_id: int, stage: str, surname: str | None = None
    ) -> None:
        async with self.connect() as db:
            if surname is None:
                await db.execute(
                    "UPDATE registration_flows SET stage=?,updated_at=? WHERE user_id=?",
                    (stage, utc_now().isoformat(), user_id),
                )
            else:
                await db.execute(
                    """UPDATE registration_flows
                       SET stage=?,surname=?,updated_at=? WHERE user_id=?""",
                    (stage, surname, utc_now().isoformat(), user_id),
                )
            await db.commit()

    async def delete_registration_flow(self, user_id: int) -> None:
        async with self.connect() as db:
            await db.execute("DELETE FROM registration_flows WHERE user_id=?", (user_id,))
            await db.commit()

    async def event_for_registration(self, post_id: int) -> dict | None:
        now = utc_now().isoformat()
        async with self.connect() as db:
            row = await (await db.execute(
                """SELECT e.*,p.text
                   FROM events e JOIN posts p ON p.id=e.post_id
                   WHERE e.post_id=? AND e.status='active' AND e.starts_at>?
                     AND EXISTS (
                         SELECT 1 FROM deliveries d
                         WHERE d.post_id=p.id AND d.status='sent'
                     )""",
                (post_id, now),
            )).fetchone()
            return dict(row) if row else None

    async def registration(self, user_id: int, post_id: int) -> dict | None:
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT * FROM registrations WHERE user_id=? AND post_id=?",
                (user_id, post_id),
            )).fetchone()
            return dict(row) if row else None

    async def register(self, user_id: int, post_id: int, reminders_enabled: bool) -> bool:
        if not await self.event_for_registration(post_id):
            return False
        now = utc_now().isoformat()
        async with self.connect() as db:
            await db.execute(
                """INSERT INTO registrations(
                       post_id,user_id,reminders_enabled,status,registered_at
                   ) VALUES(?,?,?,'registered',?)
                   ON CONFLICT(post_id,user_id) DO UPDATE SET
                       reminders_enabled=excluded.reminders_enabled,
                       status='registered', registered_at=excluded.registered_at,
                       cancelled_at=NULL, reminder_sent_at=NULL,
                       attendance_prompt_sent_at=NULL, attended=NULL,
                       attendance_recorded_at=NULL""",
                (post_id, user_id, int(reminders_enabled), now),
            )
            await db.commit()
            return True

    async def user_registrations(self, user_id: int) -> list[dict]:
        async with self.connect() as db:
            rows = await (await db.execute(
                """SELECT r.post_id,r.status,r.reminders_enabled,r.attended,
                          e.starts_at,e.ends_at,p.text
                   FROM registrations r
                   JOIN events e ON e.post_id=r.post_id
                   JOIN posts p ON p.id=r.post_id
                   WHERE r.user_id=? AND r.status='registered'
                     AND e.status='active' AND e.starts_at>?
                   ORDER BY e.starts_at""",
                (user_id, utc_now().isoformat()),
            )).fetchall()
            return [dict(row) for row in rows]

    async def cancel_registration(self, user_id: int, post_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                """UPDATE registrations SET status='cancelled',cancelled_at=?
                   WHERE user_id=? AND post_id=? AND status='registered'
                     AND EXISTS (
                         SELECT 1 FROM events e
                         WHERE e.post_id=registrations.post_id
                           AND e.status='active' AND e.starts_at>?
                     )""",
                (utc_now().isoformat(), user_id, post_id, utc_now().isoformat()),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def admin_events(self, past: bool = False) -> list[dict]:
        time_condition = "e.ends_at<=?" if past else "e.ends_at>?"
        async with self.connect() as db:
            rows = await (await db.execute(
                f"""SELECT e.post_id,e.starts_at,e.ends_at,e.status,p.text,
                          COUNT(CASE WHEN r.status='registered' THEN 1 END) AS registrations
                   FROM events e JOIN posts p ON p.id=e.post_id
                   LEFT JOIN registrations r ON r.post_id=e.post_id
                   WHERE e.status='active' AND {time_condition}
                     AND EXISTS (
                       SELECT 1 FROM deliveries d
                       WHERE d.post_id=e.post_id AND d.status='sent'
                   )
                   GROUP BY e.post_id ORDER BY e.starts_at DESC""",
                (utc_now().isoformat(),),
            )).fetchall()
            return [dict(row) for row in rows]

    async def cancel_event(self, post_id: int) -> list[dict] | None:
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                """UPDATE events SET status='cancelled',cancelled_at=?
                   WHERE post_id=? AND status='active' AND ends_at>?""",
                (utc_now().isoformat(), post_id, utc_now().isoformat()),
            )
            if cursor.rowcount != 1:
                await db.rollback()
                return None
            rows = await (await db.execute(
                """SELECT r.user_id,p.text
                   FROM registrations r JOIN posts p ON p.id=r.post_id
                   WHERE r.post_id=? AND r.status='registered'""",
                (post_id,),
            )).fetchall()
            await db.commit()
            return [dict(row) for row in rows]

    async def event_registrations(self, post_id: int) -> list[dict]:
        async with self.connect() as db:
            rows = await (await db.execute(
                """SELECT r.user_id,r.registered_at,r.reminders_enabled,r.status,r.attended,
                          u.surname,u.given_name
                   FROM registrations r
                   JOIN user_profiles u ON u.user_id=r.user_id
                   WHERE r.post_id=?
                   ORDER BY u.surname,u.given_name""",
                (post_id,),
            )).fetchall()
            return [dict(row) for row in rows]

    async def due_reminders(self, reminder_hours: int = 24) -> list[dict]:
        now = utc_now()
        horizon = (now + timedelta(hours=reminder_hours)).isoformat()
        async with self.connect() as db:
            rows = await (await db.execute(
                """SELECT r.post_id,r.user_id,e.starts_at,p.text
                   FROM registrations r
                   JOIN events e ON e.post_id=r.post_id
                   JOIN posts p ON p.id=r.post_id
                   WHERE r.status='registered' AND r.reminders_enabled=1
                     AND r.reminder_sent_at IS NULL
                     AND e.status='active'
                     AND e.starts_at>? AND e.starts_at<=?""",
                (now.isoformat(), horizon),
            )).fetchall()
            return [dict(row) for row in rows]

    async def mark_reminder_sent(self, user_id: int, post_id: int) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE registrations SET reminder_sent_at=? WHERE user_id=? AND post_id=?",
                (utc_now().isoformat(), user_id, post_id),
            )
            await db.commit()

    async def due_attendance_prompts(self) -> list[dict]:
        async with self.connect() as db:
            rows = await (await db.execute(
                """SELECT r.post_id,r.user_id,p.text
                   FROM registrations r
                   JOIN events e ON e.post_id=r.post_id
                   JOIN posts p ON p.id=r.post_id
                   WHERE r.status='registered'
                     AND r.attendance_prompt_sent_at IS NULL
                     AND e.status='active'
                     AND e.ends_at<=?""",
                (utc_now().isoformat(),),
            )).fetchall()
            return [dict(row) for row in rows]

    async def mark_attendance_prompt_sent(self, user_id: int, post_id: int) -> None:
        async with self.connect() as db:
            await db.execute(
                """UPDATE registrations SET attendance_prompt_sent_at=?
                   WHERE user_id=? AND post_id=?""",
                (utc_now().isoformat(), user_id, post_id),
            )
            await db.commit()

    async def record_attendance(self, user_id: int, post_id: int, attended: bool) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                """UPDATE registrations SET attended=?,attendance_recorded_at=?
                   WHERE user_id=? AND post_id=? AND status='registered'
                     AND EXISTS (
                         SELECT 1 FROM events e
                         WHERE e.post_id=registrations.post_id
                           AND e.status='active' AND e.ends_at<=?
                     )""",
                (
                    int(attended), utc_now().isoformat(), user_id, post_id,
                    utc_now().isoformat(),
                ),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def delivery_succeeded(self, delivery_id: int, external_id: str) -> None:
        async with self.connect() as db:
            row = await (await db.execute("SELECT post_id FROM deliveries WHERE id=?", (delivery_id,))).fetchone()
            await db.execute(
                "UPDATE deliveries SET status='sent',external_id=?,published_at=?,last_error=NULL WHERE id=?",
                (external_id, utc_now().isoformat(), delivery_id),
            )
            await self._finalize(db, row["post_id"])
            await db.commit()

    async def delivery_failed(self, delivery_id: int, error: str, max_attempts: int) -> None:
        async with self.connect() as db:
            row = await (await db.execute("SELECT post_id,attempts FROM deliveries WHERE id=?", (delivery_id,))).fetchone()
            attempts = row["attempts"] + 1
            if attempts >= max_attempts:
                status, next_at = "failed", None
            else:
                delay = min(15 * (2 ** (attempts - 1)), 900)
                status, next_at = "retry", (utc_now() + timedelta(seconds=delay)).isoformat()
            await db.execute(
                "UPDATE deliveries SET status=?,attempts=?,next_attempt_at=?,last_error=? WHERE id=?",
                (status, attempts, next_at, error[:1000], delivery_id),
            )
            await self._finalize(db, row["post_id"])
            await db.commit()

    async def _finalize(self, db: aiosqlite.Connection, post_id: int) -> None:
        rows = await (await db.execute("SELECT status FROM deliveries WHERE post_id=?", (post_id,))).fetchall()
        statuses = {row["status"] for row in rows}
        if statuses and statuses <= {"sent"}:
            await db.execute("UPDATE posts SET status='sent',completed_at=? WHERE id=?", (utc_now().isoformat(), post_id))
        elif statuses and statuses <= {"sent", "failed"} and "failed" in statuses:
            await db.execute("UPDATE posts SET status='failed',completed_at=? WHERE id=?", (utc_now().isoformat(), post_id))

    async def terminal_notifications(self) -> list[dict]:
        async with self.connect() as db:
            rows = await (await db.execute(
                "SELECT id,creator_id,status FROM posts WHERE status IN ('sent','failed') AND notified=0"
            )).fetchall()
            result: list[dict] = []
            for row in rows:
                deliveries = await (await db.execute(
                    "SELECT target_name,status,last_error FROM deliveries WHERE post_id=? ORDER BY id", (row["id"],)
                )).fetchall()
                result.append(dict(row) | {"deliveries": [dict(item) for item in deliveries]})
            return result

    async def mark_notified(self, post_id: int) -> None:
        async with self.connect() as db:
            await db.execute("UPDATE posts SET notified=1 WHERE id=?", (post_id,))
            await db.commit()
