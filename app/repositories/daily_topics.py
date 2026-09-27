from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from ..db import Database


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class DailyTopicJob:
    id: int
    scheduled_for: datetime
    attempts: int
    prompt_version: str | None


class DailyTopicRepository:
    """Durable, idempotent queue for future daily-topic generation."""

    def __init__(self, db: Database):
        self.db = db

    async def enqueue(self, scheduled_for: datetime, prompt_version: str) -> int:
        scheduled = scheduled_for.astimezone(timezone.utc).isoformat()
        now = utc_now().isoformat()
        async with self.db.connect() as connection:
            await connection.execute(
                """INSERT OR IGNORE INTO ai_topic_jobs(
                       scheduled_for,status,next_attempt_at,prompt_version,
                       created_at,updated_at
                   ) VALUES(?,'pending',?,?,?,?)""",
                (scheduled, scheduled, prompt_version, now, now),
            )
            row = await (await connection.execute(
                "SELECT id FROM ai_topic_jobs WHERE scheduled_for=?", (scheduled,)
            )).fetchone()
            await connection.commit()
            return int(row["id"])

    async def claim_due(self, now: datetime | None = None) -> DailyTopicJob | None:
        current = (now or utc_now()).astimezone(timezone.utc).isoformat()
        async with self.db.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            row = await (await connection.execute(
                """SELECT id,scheduled_for,attempts,prompt_version
                   FROM ai_topic_jobs
                   WHERE status IN ('pending','retry') AND next_attempt_at<=?
                   ORDER BY next_attempt_at,id LIMIT 1""",
                (current,),
            )).fetchone()
            if not row:
                await connection.commit()
                return None
            cursor = await connection.execute(
                """UPDATE ai_topic_jobs
                   SET status='generating',attempts=attempts+1,updated_at=?
                   WHERE id=? AND status IN ('pending','retry')""",
                (current, row["id"]),
            )
            if cursor.rowcount != 1:
                await connection.rollback()
                return None
            await connection.commit()
            return DailyTopicJob(
                id=int(row["id"]),
                scheduled_for=datetime.fromisoformat(row["scheduled_for"]),
                attempts=int(row["attempts"]) + 1,
                prompt_version=row["prompt_version"],
            )

    async def mark_scheduled(
        self, job_id: int, post_id: int, topic: dict
    ) -> None:
        async with self.db.connect() as connection:
            cursor = await connection.execute(
                """UPDATE ai_topic_jobs
                   SET status='scheduled',post_id=?,topic_json=?,last_error=NULL,
                       updated_at=?
                   WHERE id=? AND status='generating'""",
                (
                    post_id,
                    json.dumps(topic, ensure_ascii=False),
                    utc_now().isoformat(),
                    job_id,
                ),
            )
            await connection.commit()
            if cursor.rowcount != 1:
                raise RuntimeError("AI-задание уже не находится в обработке")

    async def mark_failed(
        self,
        job_id: int,
        error: str,
        *,
        retry_at: datetime | None,
    ) -> None:
        status = "retry" if retry_at else "failed"
        next_attempt = (
            retry_at.astimezone(timezone.utc).isoformat()
            if retry_at else utc_now().isoformat()
        )
        async with self.db.connect() as connection:
            cursor = await connection.execute(
                """UPDATE ai_topic_jobs
                   SET status=?,next_attempt_at=?,last_error=?,updated_at=?
                   WHERE id=? AND status='generating'""",
                (
                    status,
                    next_attempt,
                    error[:1000],
                    utc_now().isoformat(),
                    job_id,
                ),
            )
            await connection.commit()
            if cursor.rowcount != 1:
                raise RuntimeError("AI-задание уже не находится в обработке")

    async def recent_titles(self, limit: int = 30) -> list[str]:
        async with self.db.connect() as connection:
            rows = await (await connection.execute(
                """SELECT topic_json FROM ai_topic_jobs
                   WHERE status='scheduled' AND topic_json IS NOT NULL
                   ORDER BY scheduled_for DESC LIMIT ?""",
                (limit,),
            )).fetchall()
        titles: list[str] = []
        for row in rows:
            try:
                title = str(json.loads(row["topic_json"])["title"]).strip()
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if title:
                titles.append(title)
        return titles
