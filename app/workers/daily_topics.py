from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ..repositories.daily_topics import (
    DailyTopicJob,
    DailyTopicRepository,
    utc_now,
)
from ..services.daily_topics import DailyTopicService


log = logging.getLogger(__name__)


class DailyTopicWorker:
    """Processes durable topic jobs. It is activated with a concrete AI provider."""

    name = "daily_topics"

    def __init__(
        self,
        repository: DailyTopicRepository,
        service: DailyTopicService,
        *,
        creator_id: int,
        poll_interval_seconds: int = 30,
        max_attempts: int = 5,
    ):
        self.repository = repository
        self.service = service
        self.creator_id = creator_id
        self.poll_interval_seconds = max(1, poll_interval_seconds)
        self.max_attempts = max(1, max_attempts)

    async def run(self) -> None:
        while True:
            try:
                job = await self.repository.claim_due()
                if job:
                    await self._process(job)
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Daily topic worker loop failed")
            await asyncio.sleep(self.poll_interval_seconds)

    async def _process(self, job: DailyTopicJob) -> None:
        log.info(
            "Daily topic generation started: job_id=%s attempt=%s",
            job.id,
            job.attempts,
        )
        try:
            history = await self.repository.recent_history()
            options = await self.repository.preferences()
            post_id, topic = await self.service.generate_and_schedule(
                history=history,
                creator_id=self.creator_id,
                scheduled_at=max(job.scheduled_for, utc_now()),
                idempotency_key=f"daily-topic-job:{job.id}",
                options=options,
            )
            await self.repository.mark_scheduled(
                job.id, post_id, topic.as_json_value()
            )
            log.info(
                "Daily topic scheduled: job_id=%s post_id=%s title=%r",
                job.id,
                post_id,
                topic.title,
            )
        except Exception as exc:
            if job.attempts >= self.max_attempts:
                retry_at = None
            else:
                delay_minutes = min(5 * (2 ** (job.attempts - 1)), 360)
                retry_at = utc_now() + timedelta(minutes=delay_minutes)
            await self.repository.mark_failed(
                job.id, str(exc), retry_at=retry_at
            )
            log.exception(
                "Daily topic generation failed: job_id=%s attempt=%s",
                job.id,
                job.attempts,
            )


class DailyTopicPlannerWorker:
    """Keeps the next automatic topic in the durable queue."""

    name = "daily_topic_planner"
    def __init__(
        self,
        repository: DailyTopicRepository,
        *,
        publish_time: time,
        timezone_value: ZoneInfo,
        poll_interval_seconds: int = 60,
    ):
        self.repository = repository
        self.publish_time = publish_time
        self.timezone = timezone_value
        self.poll_interval_seconds = max(1, poll_interval_seconds)

    async def run(self) -> None:
        while True:
            try:
                await self.plan()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Daily topic planner loop failed")
            await asyncio.sleep(self.poll_interval_seconds)

    async def plan(self, now: datetime | None = None) -> int:
        current = (now or utc_now()).astimezone(self.timezone)
        scheduled_local = datetime.combine(
            current.date(), self.publish_time, tzinfo=self.timezone
        )
        if scheduled_local <= current:
            scheduled_local += timedelta(days=1)
        scheduled_utc = scheduled_local.astimezone(timezone.utc)
        job_id = await self.repository.enqueue(
            scheduled_utc,
            "daily-v2",
            available_at=current.astimezone(timezone.utc),
        )
        log.debug(
            "Next daily topic job planned: job_id=%s scheduled_for=%s",
            job_id,
            scheduled_utc.isoformat(),
        )
        return job_id
