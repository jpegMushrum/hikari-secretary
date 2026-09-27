from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import aiohttp

from ..services.daily_topics import (
    DailyTopic,
    GrammarPoint,
    TopicGenerationOptions,
    TopicHistoryItem,
    VocabularyItem,
)

if TYPE_CHECKING:
    from ..config import Settings


class DeepSeekError(RuntimeError):
    """DeepSeek request or response could not be processed safely."""


class DeepSeekTopicProvider:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: int = 90,
        question_count: int = 5,
        vocabulary_count: int = 10,
        grammar_count: int = 3,
        session: aiohttp.ClientSession | None = None,
    ):
        if not api_key.strip():
            raise ValueError("DEEPSEEK_API_KEY не задан")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(1, timeout_seconds)
        self.question_count = question_count
        self.vocabulary_count = vocabulary_count
        self.grammar_count = grammar_count
        self.session = session

    @classmethod
    def from_settings(cls, settings: Settings) -> DeepSeekTopicProvider:
        if not settings.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY не задан")
        return cls(
            settings.deepseek_api_key,
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
            timeout_seconds=settings.deepseek_timeout_seconds,
            question_count=settings.ai_topics.question_count,
            vocabulary_count=settings.ai_topics.vocabulary_count,
            grammar_count=settings.ai_topics.grammar_count,
        )

    async def generate(
        self,
        history: Sequence[TopicHistoryItem],
        options: TopicGenerationOptions | None = None,
    ) -> DailyTopic:
        payload = self._payload(history, options)
        if self.session:
            response = await self._request(self.session, payload)
        else:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                response = await self._request(session, payload)
        topic = self._parse_completion(response)
        requested_level = options.jlpt_level if options else "N3"
        self._validate_requested_level(topic, requested_level)
        self._validate_requested_size(topic)
        return topic

    async def _request(
        self, session: aiohttp.ClientSession, payload: dict[str, Any]
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            ) as response:
                if response.status >= 400:
                    detail = (await response.text())[:1000]
                    raise DeepSeekError(
                        f"DeepSeek HTTP {response.status}: {detail}"
                    )
                return await response.json()
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError) as exc:
            raise DeepSeekError(f"Не удалось обратиться к DeepSeek: {exc}") from exc

    def _payload(
        self,
        history: Sequence[TopicHistoryItem],
        options: TopicGenerationOptions | None = None,
    ) -> dict[str, Any]:
        level = options.jlpt_level if options else "N3"
        used = [
            {
                "conversation_topic": item.conversation_topic,
                "vocabulary_theme": item.vocabulary_theme,
            }
            for item in history
        ]
        system_prompt = (
            "Ты составляешь ежедневные материалы для разговорного клуба японского "
            "языка. Верни только JSON без Markdown. Создай одну практичную тему для "
            "разговора, тематическую лексику и полезную грамматику. Объяснения и "
            "переводы пиши по-русски, японские примеры — естественным японским. "
            "Не повторяй и не перефразируй близко темы из переданной истории. "
            f"Японский язык должен точно соответствовать JLPT {level}. "
            "Не упрощай материал до более низкого уровня и не делай его сложнее. "
            "Тема может быть бытовой, но вопросы, лексика, примеры и грамматика "
            "должны реально тренировать целевой уровень. "
            f"Укажи {level} в поле jlpt_level."
        )
        level_guidance = {
            "N5": "Используй только базовые короткие фразы и начальную грамматику.",
            "N4": "Используй элементарные связные фразы и грамматику уровня N4.",
            "N3": (
                "Это средний уровень: вопросы должны требовать объяснения причин, "
                "сравнения и выражения мнения; используй лексику и конструкции N3, "
                "а не только базовые шаблоны N5-N4."
            ),
            "N2": "Используй сложные связные высказывания и конструкции уровня N2.",
            "N1": "Используй продвинутую абстрактную лексику и конструкции N1.",
        }
        system_prompt += f" {level_guidance[level]}"
        if options and options.admin_comment:
            system_prompt += (
                " Пожелание администратора к текущему материалу: "
                f"{options.admin_comment}"
            )
        user_prompt = (
            "Уже использованные темы:\n"
            f"{json.dumps(used, ensure_ascii=False)}\n\n"
            "Сформируй JSON строго такого вида:\n"
            "{\n"
            f'  "jlpt_level": "{level}",\n'
            '  "title": "тема разговора",\n'
            '  "vocabulary_theme": "отдельная тема лексики",\n'
            '  "introduction": "краткое введение",\n'
            f'  "questions": ["ровно {self.question_count} вопросов для разговора"],\n'
            '  "vocabulary": [{"japanese": "слово", "reading": "чтение", '
            '"translation": "перевод"}],\n'
            '  "grammar": [{"pattern": "конструкция", '
            '"explanation": "объяснение", "example": "пример", '
            '"translation": "перевод примера"}]\n'
            "}\n"
            f"Дай ровно {self.vocabulary_count} слов и ровно "
            f"{self.grammar_count} грамматических конструкций."
        )
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 3000,
            "stream": False,
        }

    def _validate_requested_size(self, topic: DailyTopic) -> None:
        expected = (
            ("вопросов", len(topic.questions), self.question_count),
            ("слов", len(topic.vocabulary), self.vocabulary_count),
            ("грамматических конструкций", len(topic.grammar), self.grammar_count),
        )
        for label, actual, requested in expected:
            if actual != requested:
                raise DeepSeekError(
                    f"DeepSeek вернул {actual} {label}, ожидалось {requested}"
                )

    @staticmethod
    def _validate_requested_level(topic: DailyTopic, requested: str) -> None:
        if topic.jlpt_level != requested:
            raise DeepSeekError(
                f"DeepSeek вернул уровень {topic.jlpt_level}, ожидался {requested}"
            )

    @classmethod
    def _parse_completion(cls, response: dict[str, Any]) -> DailyTopic:
        try:
            choice = response["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise DeepSeekError(
                    "DeepSeek не завершил ответ: "
                    f"finish_reason={choice.get('finish_reason')!r}"
                )
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise DeepSeekError("DeepSeek вернул пустой ответ")
            value = json.loads(content)
        except DeepSeekError:
            raise
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise DeepSeekError("DeepSeek вернул некорректный JSON") from exc

        try:
            return DailyTopic(
                title=cls._text(value, "title"),
                vocabulary_theme=cls._text(value, "vocabulary_theme"),
                introduction=cls._text(value, "introduction"),
                questions=tuple(cls._string_list(value, "questions")),
                vocabulary=tuple(
                    VocabularyItem(
                        cls._text(item, "japanese"),
                        cls._text(item, "reading"),
                        cls._text(item, "translation"),
                    )
                    for item in cls._object_list(value, "vocabulary")
                ),
                grammar=tuple(
                    GrammarPoint(
                        cls._text(item, "pattern"),
                        cls._text(item, "explanation"),
                        cls._text(item, "example"),
                        cls._text(item, "translation"),
                    )
                    for item in cls._object_list(value, "grammar")
                ),
                jlpt_level=cls._text(value, "jlpt_level").upper(),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DeepSeekError("Структура ответа DeepSeek не соответствует схеме") from exc

    @staticmethod
    def _text(value: dict[str, Any], key: str) -> str:
        result = value[key]
        if not isinstance(result, str) or not result.strip():
            raise ValueError(key)
        return result.strip()

    @staticmethod
    def _string_list(value: dict[str, Any], key: str) -> list[str]:
        result = value[key]
        if not isinstance(result, list) or not all(
            isinstance(item, str) and item.strip() for item in result
        ):
            raise ValueError(key)
        return [item.strip() for item in result]

    @staticmethod
    def _object_list(value: dict[str, Any], key: str) -> list[dict[str, Any]]:
        result = value[key]
        if not isinstance(result, list) or not all(
            isinstance(item, dict) for item in result
        ):
            raise ValueError(key)
        return result
