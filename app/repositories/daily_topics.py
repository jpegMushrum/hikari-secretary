from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from ..db import Database
from ..services.daily_topics import TopicGenerationOptions, TopicHistoryItem


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

    async def enqueue(
        self,
        scheduled_for: datetime,
        prompt_version: str,
        *,
        available_at: datetime | None = None,
    ) -> int:
        scheduled = scheduled_for.astimezone(timezone.utc).isoformat()
        available = (available_at or scheduled_for).astimezone(timezone.utc).isoformat()
        now = utc_now().isoformat()
        async with self.db.connect() as connection:
            await connection.execute(
                """INSERT OR IGNORE INTO ai_topic_jobs(
                       scheduled_for,status,next_attempt_at,prompt_version,
                       created_at,updated_at
                   ) VALUES(?,'pending',?,?,?,?)""",
                (scheduled, available, prompt_version, now, now),
            )
            # A changed generation strategy may recover a failed job for this
            # publication slot once, without creating a duplicate publication.
            await connection.execute(
                """UPDATE ai_topic_jobs
                   SET status='pending',attempts=0,next_attempt_at=?,
                       prompt_version=?,last_error=NULL,updated_at=?
                   WHERE scheduled_for=? AND status='failed'
                     AND prompt_version IS NOT ?""",
                (available, prompt_version, now, scheduled, prompt_version),
            )
            row = await (await connection.execute(
                "SELECT id FROM ai_topic_jobs WHERE scheduled_for=?", (scheduled,)
            )).fetchone()
            await connection.commit()
            return int(row["id"])

    async def preferences(self) -> TopicGenerationOptions:
        async with self.db.connect() as connection:
            row = await (await connection.execute(
                "SELECT jlpt_level,admin_comment FROM ai_topic_settings WHERE id=1"
            )).fetchone()
        if not row:
            raise RuntimeError("Настройки AI-тем не инициализированы")
        return TopicGenerationOptions(row["jlpt_level"], row["admin_comment"])

    async def save_preferences(
        self, options: TopicGenerationOptions, updated_by: int
    ) -> None:
        if options.jlpt_level not in {"N5", "N4", "N3", "N2", "N1"}:
            raise ValueError("Некорректный уровень JLPT")
        comment = options.admin_comment.strip() if options.admin_comment else None
        if comment and len(comment) > 500:
            raise ValueError("Комментарий не должен превышать 500 символов")
        async with self.db.connect() as connection:
            await connection.execute(
                """UPDATE ai_topic_settings
                   SET jlpt_level=?,admin_comment=?,updated_by=?,updated_at=?
                   WHERE id=1""",
                (
                    options.jlpt_level,
                    comment,
                    updated_by,
                    utc_now().isoformat(),
                ),
            )
            await connection.commit()

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

    async def recent_history(
        self, limit: int | None = None, *, exclude_post_id: int | None = None
    ) -> list[TopicHistoryItem]:
        limit_sql = " LIMIT ?" if limit is not None else ""
        where = "status='scheduled' AND topic_json IS NOT NULL"
        parameters: tuple = ()
        if exclude_post_id is not None:
            where += " AND (post_id IS NULL OR post_id<>?)"
            parameters += (exclude_post_id,)
        if limit is not None:
            parameters += (max(1, limit),)
        async with self.db.connect() as connection:
            rows = await (await connection.execute(
                """SELECT topic_json FROM ai_topic_jobs
                   WHERE """ + where + """
                   ORDER BY scheduled_for DESC""" + limit_sql,
                parameters,
            )).fetchall()
        history: list[TopicHistoryItem] = []
        for row in rows:
            try:
                topic = json.loads(row["topic_json"])
                title = str(topic["title"]).strip()
                vocabulary_theme = str(topic["vocabulary_theme"]).strip()
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if title and vocabulary_theme:
                history.append(TopicHistoryItem(title, vocabulary_theme))
        return history

    async def replace_topic_for_post(self, post_id: int, topic: dict) -> bool:
        async with self.db.connect() as connection:
            cursor = await connection.execute(
                """UPDATE ai_topic_jobs SET topic_json=?,updated_at=?
                   WHERE post_id=? AND status='scheduled'""",
                (
                    json.dumps(topic, ensure_ascii=False),
                    utc_now().isoformat(),
                    post_id,
                ),
            )
            await connection.commit()
            return cursor.rowcount == 1

    async def record_manual_publication(
        self, post_id: int, topic: dict, prompt_version: str = "admin-v1"
    ) -> int:
        """Persist a manually approved topic in history, idempotently by post."""
        now = utc_now().isoformat()
        async with self.db.connect() as connection:
            existing = await (await connection.execute(
                "SELECT id FROM ai_topic_jobs WHERE post_id=?", (post_id,)
            )).fetchone()
            if existing:
                return int(existing["id"])
            cursor = await connection.execute(
                """INSERT INTO ai_topic_jobs(
                       scheduled_for,status,attempts,next_attempt_at,prompt_version,
                       topic_json,post_id,created_at,updated_at
                   ) VALUES(?,'scheduled',1,?,?,?,?,?,?)""",
                (
                    now,
                    now,
                    prompt_version,
                    json.dumps(topic, ensure_ascii=False),
                    post_id,
                    now,
                    now,
                ),
            )
            await connection.commit()
            return int(cursor.lastrowid)
