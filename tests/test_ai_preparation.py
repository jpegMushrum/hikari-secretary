import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.config import Target
from app.db import Database
from app.repositories.daily_topics import DailyTopicJob, DailyTopicRepository
from app.services.daily_topics import (
    DailyTopic,
    DailyTopicRenderer,
    DailyTopicService,
    VocabularyItem,
)
from app.services.publications import PublicationService
from app.workers.daily_topics import DailyTopicWorker
from migrations.runner import migrate


async def database_at(path: Path) -> Database:
    migrate(path, create_backup=False)
    database = Database(path)
    await database.initialize()
    return database


class PublicationServiceTests(unittest.TestCase):
    def test_automated_publication_is_created_atomically(self) -> None:
        asyncio.run(self._automated_publication_is_created_atomically())

    async def _automated_publication_is_created_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = await database_at(Path(directory) / "bot.sqlite3")
            target = Target(0, "chat", "Чат", "-100123", 42)
            service = PublicationService(database, (target,))
            when = datetime.now(timezone.utc)

            post_id = await service.create_scheduled(
                creator_id=100,
                text="Тема дня",
                target_keys=("chat",),
                scheduled_at=when,
                source="ai_daily_topic",
                idempotency_key="daily-topic:2026-09-28",
            )

            duplicate_id = await service.create_scheduled(
                creator_id=100,
                text="Другой ответ при повторной попытке",
                target_keys=("chat",),
                scheduled_at=when,
                source="ai_daily_topic",
                idempotency_key="daily-topic:2026-09-28",
            )

            post = await database.post(post_id)
            self.assertEqual(duplicate_id, post_id)
            self.assertEqual(post["status"], "scheduled")
            self.assertEqual(post["source"], "ai_daily_topic")
            self.assertEqual(post["deliveries"][0]["message_thread_id"], 42)
            delivery = await database.claim_due()
            self.assertEqual(delivery.post_id, post_id)

    def test_unknown_target_does_not_create_a_post(self) -> None:
        asyncio.run(self._unknown_target_does_not_create_a_post())

    async def _unknown_target_does_not_create_a_post(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = await database_at(Path(directory) / "bot.sqlite3")
            service = PublicationService(database, ())

            with self.assertRaisesRegex(ValueError, "Неизвестные цели"):
                await service.create_scheduled(
                    creator_id=100,
                    text="Тема",
                    target_keys=("missing",),
                    scheduled_at=datetime.now(timezone.utc),
                    source="ai_daily_topic",
                )

            async with database.connect() as connection:
                count = (await (await connection.execute(
                    "SELECT COUNT(*) AS n FROM posts"
                )).fetchone())["n"]
            self.assertEqual(count, 0)


class DailyTopicPreparationTests(unittest.TestCase):
    @staticmethod
    def _topic() -> DailyTopic:
        return DailyTopic(
            title="Любимые блюда",
            introduction="Обсудим еду и вкусы.",
            questions=("Что вы любите готовить?",),
            vocabulary=(
                VocabularyItem("料理", "りょうり", "блюдо; кулинария"),
            ),
        )

    def test_topic_is_validated_rendered_and_scheduled(self) -> None:
        topic = self._topic()
        provider = SimpleNamespace(generate=AsyncMock(return_value=topic))
        publications = SimpleNamespace(create_scheduled=AsyncMock(return_value=15))
        service = DailyTopicService(provider, publications)
        when = datetime.now(timezone.utc) + timedelta(hours=1)

        post_id, generated = asyncio.run(service.generate_and_schedule(
            recent_titles=("Путешествия",),
            creator_id=100,
            target_keys=("chat",),
            scheduled_at=when,
            idempotency_key="daily-topic-job:10",
        ))

        self.assertEqual(post_id, 15)
        self.assertEqual(generated, topic)
        provider.generate.assert_awaited_once_with(("Путешествия",))
        call = publications.create_scheduled.await_args.kwargs
        self.assertEqual(call["source"], "ai_daily_topic")
        self.assertEqual(call["idempotency_key"], "daily-topic-job:10")
        self.assertIn("料理（りょうり）", call["text"])

    def test_renderer_rejects_incomplete_topic(self) -> None:
        topic = DailyTopic("", "Описание", ("Вопрос?",), self._topic().vocabulary)
        with self.assertRaisesRegex(ValueError, "Название"):
            DailyTopicRenderer().render(topic)

    def test_job_queue_is_idempotent_and_keeps_topic_history(self) -> None:
        asyncio.run(self._job_queue_is_idempotent_and_keeps_topic_history())

    async def _job_queue_is_idempotent_and_keeps_topic_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = await database_at(Path(directory) / "bot.sqlite3")
            repository = DailyTopicRepository(database)
            scheduled = datetime.now(timezone.utc) - timedelta(minutes=1)

            first = await repository.enqueue(scheduled, "v1")
            second = await repository.enqueue(scheduled, "v1")
            self.assertEqual(first, second)

            job = await repository.claim_due()
            self.assertIsNotNone(job)
            self.assertEqual(job.attempts, 1)
            self.assertIsNone(await repository.claim_due())

            post_id = await database.create_post(100, "Тема", [], [])
            await repository.mark_scheduled(
                job.id, post_id, self._topic().as_json_value()
            )
            self.assertEqual(await repository.recent_titles(), ["Любимые блюда"])

    def test_worker_passes_stable_idempotency_key(self) -> None:
        topic = self._topic()
        repository = SimpleNamespace(
            recent_titles=AsyncMock(return_value=["Путешествия"]),
            mark_scheduled=AsyncMock(),
            mark_failed=AsyncMock(),
        )
        service = SimpleNamespace(
            generate_and_schedule=AsyncMock(return_value=(17, topic))
        )
        worker = DailyTopicWorker(
            repository,
            service,
            creator_id=100,
            target_keys=("chat",),
        )
        job = DailyTopicJob(
            id=8,
            scheduled_for=datetime.now(timezone.utc),
            attempts=1,
            prompt_version="v1",
        )

        asyncio.run(worker._process(job))

        call = service.generate_and_schedule.await_args.kwargs
        self.assertEqual(call["idempotency_key"], "daily-topic-job:8")
        self.assertEqual(call["recent_titles"], ["Путешествия"])
        repository.mark_scheduled.assert_awaited_once_with(
            8, 17, topic.as_json_value()
        )
        repository.mark_failed.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
