from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol, Sequence

from aiogram.types import InputRichMessage

from .publications import PublicationService


@dataclass(frozen=True, slots=True)
class VocabularyItem:
    japanese: str
    reading: str
    translation: str


@dataclass(frozen=True, slots=True)
class GrammarPoint:
    pattern: str
    explanation: str
    example: str
    translation: str


@dataclass(frozen=True, slots=True)
class TopicHistoryItem:
    conversation_topic: str
    vocabulary_theme: str


@dataclass(frozen=True, slots=True)
class TopicGenerationOptions:
    jlpt_level: str
    admin_comment: str | None = None


@dataclass(frozen=True, slots=True)
class DailyTopic:
    title: str
    vocabulary_theme: str
    introduction: str
    questions: tuple[str, ...]
    vocabulary: tuple[VocabularyItem, ...]
    grammar: tuple[GrammarPoint, ...]

    def as_json_value(self) -> dict:
        return asdict(self)


class DailyTopicProvider(Protocol):
    """Port implemented by a concrete provider such as DeepSeek."""

    async def generate(
        self,
        history: Sequence[TopicHistoryItem],
        options: TopicGenerationOptions | None = None,
    ) -> DailyTopic: ...


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
        lines.extend(("", "🧩 Грамматика:"))
        for item in topic.grammar:
            lines.extend((
                f"• {item.pattern} — {item.explanation}",
                f"  {item.example}",
                f"  {item.translation}",
            ))
        text = "\n".join(lines)
        if len(text) > self.TELEGRAM_TEXT_LIMIT:
            raise ValueError("Сгенерированная тема превышает лимит Telegram")
        return text

    def rich_message(self, topic: DailyTopic) -> dict:
        self._validate(topic)
        vocabulary = "\n".join(
            f"• {item.japanese}（{item.reading}）— {item.translation}"
            for item in topic.vocabulary
        )
        grammar_parts: list[str] = []
        for item in topic.grammar:
            grammar_parts.append(
                f"• {item.pattern} — {item.explanation}\n"
                f"  {item.example}\n"
                f"  {item.translation}"
            )
        value = {
            "blocks": [
                {"type": "heading", "text": "🗣 Тема дня", "size": 2},
                {
                    "type": "paragraph",
                    "text": f"{topic.title}\n\n{topic.introduction}",
                },
                {
                    "type": "heading",
                    "text": "💬 Вопросы на обсуждение",
                    "size": 2,
                },
                {
                    "type": "paragraph",
                    "text": "\n".join(
                        f"• {question}" for question in topic.questions
                    ),
                },
                {
                    "type": "details",
                    "summary": "📚 Полезная лексика",
                    "blocks": [{"type": "paragraph", "text": vocabulary}],
                    "is_open": False,
                },
                {
                    "type": "details",
                    "summary": "🧩 Полезная грамматика",
                    "blocks": [{
                        "type": "paragraph",
                        "text": "\n\n".join(grammar_parts),
                    }],
                    "is_open": False,
                },
            ]
        }
        return InputRichMessage.model_validate(value).model_dump(
            mode="json", exclude_none=True
        )

    @staticmethod
    def _validate(topic: DailyTopic) -> None:
        if not topic.title.strip() or len(topic.title) > 160:
            raise ValueError("Название темы должно содержать от 1 до 160 символов")
        if not topic.introduction.strip():
            raise ValueError("У темы должно быть вступление")
        if not topic.vocabulary_theme.strip() or len(topic.vocabulary_theme) > 160:
            raise ValueError("Тема лексики должна содержать от 1 до 160 символов")
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
        if not 1 <= len(topic.grammar) <= 8:
            raise ValueError("Нужно от 1 до 8 грамматических конструкций")
        if any(
            not value.strip()
            for item in topic.grammar
            for value in (
                item.pattern,
                item.explanation,
                item.example,
                item.translation,
            )
        ):
            raise ValueError("Поля грамматики не должны быть пустыми")


class DailyTopicService:
    """Generates a validated topic and submits it to the publication queue."""

    def __init__(
        self,
        provider: DailyTopicProvider,
        publications: PublicationService,
        target_key: str,
        renderer: DailyTopicRenderer | None = None,
    ):
        if not target_key.strip():
            raise ValueError("Для AI-тем не задана цель публикации")
        self.provider = provider
        self.publications = publications
        self.target_key = target_key
        self.renderer = renderer or DailyTopicRenderer()

    async def generate_and_schedule(
        self,
        *,
        history: Sequence[TopicHistoryItem],
        creator_id: int,
        scheduled_at: datetime,
        idempotency_key: str,
        options: TopicGenerationOptions | None = None,
    ) -> tuple[int, DailyTopic]:
        topic = await self.generate(history, options)
        post_id = await self.schedule(
            topic,
            creator_id=creator_id,
            scheduled_at=scheduled_at,
            idempotency_key=idempotency_key,
        )
        return post_id, topic

    async def generate(
        self,
        history: Sequence[TopicHistoryItem],
        options: TopicGenerationOptions | None = None,
    ) -> DailyTopic:
        topic = await self.provider.generate(history, options)
        used_conversation_topics = {
            self._normalize(item.conversation_topic) for item in history
        }
        used_vocabulary_themes = {
            self._normalize(item.vocabulary_theme) for item in history
        }
        if self._normalize(topic.title) in used_conversation_topics:
            raise ValueError("Модель повторила уже использованную тему разговора")
        if self._normalize(topic.vocabulary_theme) in used_vocabulary_themes:
            raise ValueError("Модель повторила уже использованную тему лексики")
        self.renderer.render(topic)
        return topic

    async def schedule(
        self,
        topic: DailyTopic,
        *,
        creator_id: int,
        scheduled_at: datetime,
        idempotency_key: str,
    ) -> int:
        text = self.renderer.render(topic)
        rich_message = self.renderer.rich_message(topic)
        return await self.publications.create_scheduled(
            creator_id=creator_id,
            text=text,
            target_keys=(self.target_key,),
            scheduled_at=scheduled_at,
            source="ai_daily_topic",
            idempotency_key=idempotency_key,
            rich_message=rich_message,
        )

    async def replace_scheduled(self, post_id: int, topic: DailyTopic) -> bool:
        text = self.renderer.render(topic)
        rich_message = self.renderer.rich_message(topic)
        return await self.publications.replace_scheduled(
            post_id, text=text, rich_message=rich_message
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())
