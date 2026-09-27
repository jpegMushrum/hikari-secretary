import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.config import Target
from app.db import Database
from app.integrations.deepseek import DeepSeekTopicProvider
from app.handlers.ai_topics import AiTopicHandlers
from app.repositories.daily_topics import DailyTopicJob, DailyTopicRepository
from app.services.daily_topics import (
    DailyTopic,
    DailyTopicRenderer,
    DailyTopicService,
    GrammarPoint,
    TopicHistoryItem,
    TopicGenerationOptions,
    VocabularyItem,
)
from app.services.publications import PublicationService
from app.runtime import AiTopicPreview, RuntimeState
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
            vocabulary_theme="Приготовление еды",
            introduction="Обсудим еду и вкусы.",
            questions=("Что вы любите готовить?",),
            vocabulary=(
                VocabularyItem("料理", "りょうり", "блюдо; кулинария"),
            ),
            grammar=(
                GrammarPoint(
                    "〜ことが好き", "любить что-либо", "料理することが好きです。",
                    "Я люблю готовить.",
                ),
            ),
        )

    def test_topic_is_validated_rendered_and_scheduled(self) -> None:
        topic = self._topic()
        provider = SimpleNamespace(generate=AsyncMock(return_value=topic))
        publications = SimpleNamespace(create_scheduled=AsyncMock(return_value=15))
        service = DailyTopicService(provider, publications, "ai_chat")
        when = datetime.now(timezone.utc) + timedelta(hours=1)

        post_id, generated = asyncio.run(service.generate_and_schedule(
            history=(TopicHistoryItem("Путешествия", "Транспорт"),),
            creator_id=100,
            scheduled_at=when,
            idempotency_key="daily-topic-job:10",
        ))

        self.assertEqual(post_id, 15)
        self.assertEqual(generated, topic)
        provider.generate.assert_awaited_once_with(
            (TopicHistoryItem("Путешествия", "Транспорт"),), None
        )
        call = publications.create_scheduled.await_args.kwargs
        self.assertEqual(call["source"], "ai_daily_topic")
        self.assertEqual(call["target_keys"], ("ai_chat",))
        self.assertEqual(call["idempotency_key"], "daily-topic-job:10")
        self.assertIn("料理（りょうり）", call["text"])

    def test_renderer_rejects_incomplete_topic(self) -> None:
        topic = DailyTopic(
            title="",
            vocabulary_theme="Тема",
            introduction="Описание",
            questions=("Вопрос?",),
            vocabulary=self._topic().vocabulary,
            grammar=self._topic().grammar,
        )
        with self.assertRaisesRegex(ValueError, "Название"):
            DailyTopicRenderer().render(topic)

    def test_service_rejects_repeated_vocabulary_theme(self) -> None:
        topic = self._topic()
        provider = SimpleNamespace(generate=AsyncMock(return_value=topic))
        publications = SimpleNamespace(create_scheduled=AsyncMock())
        service = DailyTopicService(provider, publications, "ai_chat")

        with self.assertRaisesRegex(ValueError, "тему лексики"):
            asyncio.run(service.generate_and_schedule(
                history=(TopicHistoryItem(
                    "Другая тема", "  ПРИГОТОВЛЕНИЕ   ЕДЫ "
                ),),
                creator_id=100,
                scheduled_at=datetime.now(timezone.utc),
                idempotency_key="daily-topic-job:11",
            ))

        publications.create_scheduled.assert_not_awaited()

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
            self.assertEqual(await repository.recent_history(), [
                TopicHistoryItem("Любимые блюда", "Приготовление еды")
            ])

    def test_manual_publication_is_recorded_in_history_idempotently(self) -> None:
        asyncio.run(self._manual_publication_is_recorded_in_history_idempotently())

    async def _manual_publication_is_recorded_in_history_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = await database_at(Path(directory) / "bot.sqlite3")
            repository = DailyTopicRepository(database)
            post_id = await database.create_post(100, "Тема", [], [])

            first = await repository.record_manual_publication(
                post_id, self._topic().as_json_value()
            )
            second = await repository.record_manual_publication(
                post_id, self._topic().as_json_value()
            )

            self.assertEqual(first, second)
            self.assertEqual(await repository.recent_history(), [
                TopicHistoryItem("Любимые блюда", "Приготовление еды")
            ])

    def test_worker_passes_stable_idempotency_key(self) -> None:
        topic = self._topic()
        repository = SimpleNamespace(
            recent_history=AsyncMock(return_value=[
                TopicHistoryItem("Путешествия", "Транспорт")
            ]),
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
        self.assertEqual(call["history"], [
            TopicHistoryItem("Путешествия", "Транспорт")
        ])
        repository.mark_scheduled.assert_awaited_once_with(
            8, 17, topic.as_json_value()
        )
        repository.mark_failed.assert_not_awaited()

    def test_deepseek_prompt_contains_previous_vocabulary_themes(self) -> None:
        provider = DeepSeekTopicProvider(
            "secret",
            question_count=5,
            vocabulary_count=10,
            grammar_count=3,
        )
        payload = provider._payload(
            (
                TopicHistoryItem("Путешествия", "Транспорт и билеты"),
                TopicHistoryItem("Ресторан", "Заказ еды"),
            ),
            TopicGenerationOptions("N4", "Короткие разговорные фразы"),
        )

        prompt = payload["messages"][1]["content"]
        self.assertIn("Транспорт и билеты", prompt)
        self.assertIn("Заказ еды", prompt)
        self.assertIn("ровно 5 вопросов", prompt)
        self.assertIn("ровно 10 слов", prompt)
        system_prompt = payload["messages"][0]["content"]
        self.assertIn("JLPT N4", system_prompt)
        self.assertIn("Короткие разговорные фразы", system_prompt)
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_target_matches_only_configured_chat_and_topic(self) -> None:
        target = Target(0, "ai", "AI chat", "-100123", 42)

        self.assertTrue(target.matches(-100123, 42))
        self.assertFalse(target.matches(-100123, 43))
        self.assertFalse(target.matches(-100999, 42))

    def test_deepseek_json_is_converted_to_validated_topic(self) -> None:
        topic = self._topic()
        response = {
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        topic.as_json_value(), ensure_ascii=False
                    )
                },
            }]
        }

        parsed = DeepSeekTopicProvider._parse_completion(response)

        self.assertEqual(parsed, topic)

    def test_admin_level_and_comment_override_prompt_defaults(self) -> None:
        provider = DeepSeekTopicProvider("secret")

        payload = provider._payload(
            (), TopicGenerationOptions("N2", "Тема о собеседовании на работу")
        )

        prompt = payload["messages"][0]["content"]
        self.assertIn("JLPT N2", prompt)
        self.assertIn("Тема о собеседовании на работу", prompt)
        self.assertNotIn("JLPT N4", prompt)

    def test_admin_preview_is_published_and_added_to_history(self) -> None:
        topic = self._topic()
        service = SimpleNamespace(
            generate=AsyncMock(return_value=topic),
            schedule=AsyncMock(return_value=25),
            renderer=DailyTopicRenderer(),
        )
        repository = SimpleNamespace(
            recent_history=AsyncMock(return_value=[]),
            record_manual_publication=AsyncMock(return_value=7),
        )
        access = SimpleNamespace(guard_callback=AsyncMock(return_value=True))
        context = SimpleNamespace(
            state=RuntimeState(),
            settings=SimpleNamespace(ai_topics=SimpleNamespace()),
        )
        handlers = AiTopicHandlers(context, access, service, repository)
        status = SimpleNamespace(edit_text=AsyncMock())
        message = SimpleNamespace(answer=AsyncMock(return_value=status), edit_text=AsyncMock())
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=100),
            message=message,
            answer=AsyncMock(),
        )

        asyncio.run(handlers.generate(callback))

        self.assertIn(100, context.state.ai_topic_previews)
        service.generate.assert_awaited_once_with(
            [], TopicGenerationOptions("N3", None)
        )
        status.edit_text.assert_awaited_once()

        asyncio.run(handlers.publish(callback))

        service.schedule.assert_awaited_once()
        repository.record_manual_publication.assert_awaited_once_with(
            25, topic.as_json_value()
        )
        self.assertNotIn(100, context.state.ai_topic_previews)


if __name__ == "__main__":
    unittest.main()
