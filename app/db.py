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
    platform: str
    target_key: str
    target_name: str
    destination: str
    message_thread_id: int | None
    text: str
    entities: list[dict]
    media_paths: list[str]
    attempts: int


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
                """
            )
            columns = {
                row["name"]
                for row in await (await db.execute("PRAGMA table_info(deliveries)")).fetchall()
            }
            if "message_thread_id" not in columns:
                await db.execute("ALTER TABLE deliveries ADD COLUMN message_thread_id INTEGER")
            await db.execute(
                "UPDATE deliveries SET status='retry', next_attempt_at=? WHERE status='publishing'",
                (utc_now().isoformat(),),
            )
            await db.commit()

    async def create_post(self, creator_id: int, text: str, entities: list[dict], media_paths: list[str]) -> int:
        async with self.connect() as db:
            cursor = await db.execute(
                "INSERT INTO posts(creator_id,text,entities_json,created_at) VALUES(?,?,?,?)",
                (creator_id, text, json.dumps(entities, ensure_ascii=False), utc_now().isoformat()),
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
            return dict(post) | {
                "entities": json.loads(post["entities_json"]),
                "media_paths": [row["path"] for row in media],
                "deliveries": [dict(row) for row in deliveries],
            }

    async def toggle_delivery(
        self,
        post_id: int,
        platform: str,
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
                    (post_id, platform, target_key, target_name, destination, message_thread_id),
                )
            await db.commit()

    async def schedule(self, post_id: int, when: datetime) -> bool:
        async with self.connect() as db:
            count = await (await db.execute("SELECT COUNT(*) AS n FROM deliveries WHERE post_id=?", (post_id,))).fetchone()
            if not count or count["n"] == 0:
                return False
            cursor = await db.execute(
                "UPDATE posts SET status='scheduled', scheduled_at=? WHERE id=? AND status='draft'",
                (when.astimezone(timezone.utc).isoformat(), post_id),
            )
            await db.execute(
                "UPDATE deliveries SET next_attempt_at=? WHERE post_id=?",
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
                """SELECT d.id,d.post_id,d.platform,d.target_key,d.target_name,d.destination,
                          d.message_thread_id,d.attempts,
                          p.creator_id,p.text,p.entities_json
                   FROM deliveries d JOIN posts p ON p.id=d.post_id
                   WHERE p.status='scheduled' AND d.status IN ('pending','retry')
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
                platform=row["platform"], target_key=row["target_key"], target_name=row["target_name"],
                destination=row["destination"],
                message_thread_id=row["message_thread_id"],
                text=row["text"], entities=json.loads(row["entities_json"]),
                media_paths=[item["path"] for item in media], attempts=row["attempts"],
            )

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
