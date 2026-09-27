from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol, Sequence

from .publications import PublicationService


@dataclass(frozen=True, slots=True)
class VocabularyItem:
    japanese: str
    reading: str
    translation: str


@dataclass(frozen=True, slots=True)
class DailyTopic:
    title: str
    introduction: str
    questions: tuple[str, ...]
    vocabulary: tuple[VocabularyItem, ...]

    def as_json_value(self) -> dict:
        return asdict(self)


class DailyTopicProvider(Protocol):
    """Port implemented by a concrete provider such as DeepSeek."""

    async def generate(self, recent_titles: Sequence[str]) -> DailyTopic: ...


class DailyTopicRenderer:
    TELEGRAM_TEXT_LIMIT = 4096

    def render(self, topic: DailyTopic) -> str:
        self._validate(topic)
        lines = [f"🗣 Тема дня: {topic.title}", "", topic.introduction]
        lines.extend(("", "💬 Вопросы для обсуждения:"))
        lines.extend(f"• {question}" for question in topic.questions)
        lines.extend(("", "📚 Полезная лексика:"))
        lines.extend(
            f"• {item.japanese}（{item.reading}）— {item.translation}"
            for item in topic.vocabulary
        )
        text = "\n".join(lines)
        if len(text) > self.TELEGRAM_TEXT_LIMIT:
            raise ValueError("Сгенерированная тема превышает лимит Telegram")
        return text

    @staticmethod
    def _validate(topic: DailyTopic) -> None:
        if not topic.title.strip() or len(topic.title) > 160:
            raise ValueError("Название темы должно содержать от 1 до 160 символов")
        if not topic.introduction.strip():
            raise ValueError("У темы должно быть вступление")
        if not 1 <= len(topic.questions) <= 8:
            raise ValueError("Нужно от 1 до 8 вопросов")
        if any(not question.strip() for question in topic.questions):
            raise ValueError("Вопросы не должны быть пустыми")
        if not 1 <= len(topic.vocabulary) <= 20:
            raise ValueError("Нужно от 1 до 20 слов")
        if any(
            not value.strip()
            for item in topic.vocabulary
            for value in (item.japanese, item.reading, item.translation)
        ):
            raise ValueError("Поля словаря не должны быть пустыми")


class DailyTopicService:
    """Generates a validated topic and submits it to the publication queue."""

    def __init__(
        self,
        provider: DailyTopicProvider,
        publications: PublicationService,
        renderer: DailyTopicRenderer | None = None,
    ):
        self.provider = provider
        self.publications = publications
        self.renderer = renderer or DailyTopicRenderer()

    async def generate_and_schedule(
        self,
        *,
        recent_titles: Sequence[str],
        creator_id: int,
        target_keys: tuple[str, ...],
        scheduled_at: datetime,
        idempotency_key: str,
    ) -> tuple[int, DailyTopic]:
        topic = await self.provider.generate(recent_titles)
        text = self.renderer.render(topic)
        post_id = await self.publications.create_scheduled(
            creator_id=creator_id,
            text=text,
            target_keys=target_keys,
            scheduled_at=scheduled_at,
            source="ai_daily_topic",
            idempotency_key=idempotency_key,
        )
        return post_id, topic
