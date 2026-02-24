"""
Клиент для DeepSeek API с поддержкой:
  - JSON mode (response_format: json_object)
  - Retry logic с exponential backoff (tenacity)
  - Метрики cache hit для мониторинга
  - Pydantic-валидация ответов

Использует OpenAI-compatible SDK (DeepSeek API совместим с OpenAI).
"""

import json
import logging
import re
from typing import Type, TypeVar

from openai import APIConnectionError, APITimeoutError, OpenAI
from pydantic import BaseModel, ValidationError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MD_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?", re.MULTILINE)


class DeepSeekClient:
    """Клиент DeepSeek API, оптимизированный для Harvester v1."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        self._total_calls = 0
        self._cache_hits = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (json.JSONDecodeError, ValidationError, APIConnectionError, APITimeoutError)
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def classify(
        self,
        system_prompt: str,
        user_message: str,
        output_model: Type[T],
    ) -> T:
        """
        Отправляет запрос к DeepSeek и парсит ответ в Pydantic-модель.

        Args:
            system_prompt: Полный system prompt (справочники + правила + schema + examples)
            user_message: Динамический user message с raw_text
            output_model: Pydantic-модель для десериализации ответа

        Returns:
            Провалидированный экземпляр output_model

        Raises:
            json.JSONDecodeError: если ответ не парсится (retried)
            ValidationError: если JSON не проходит Pydantic-валидацию (retried)
        """
        self._total_calls += 1

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=False,
        )

        usage = response.usage
        if usage:
            self._total_input_tokens += usage.prompt_tokens
            self._total_output_tokens += usage.completion_tokens

            cache_hit_tokens = getattr(usage, "prompt_cache_hit_tokens", 0)
            if cache_hit_tokens and cache_hit_tokens > 0:
                self._cache_hits += 1
                logger.info(
                    "Cache HIT: %d/%d tokens cached (%.1f%%)",
                    cache_hit_tokens,
                    usage.prompt_tokens,
                    cache_hit_tokens / usage.prompt_tokens * 100,
                )

        raw_content = response.choices[0].message.content
        if raw_content is None:
            raise json.JSONDecodeError("Empty response from DeepSeek", "", 0)

        raw_content = raw_content.strip()

        raw_content = _strip_markdown_fences(raw_content)

        parsed = json.loads(raw_content)
        result = output_model.model_validate(parsed)

        title = getattr(result, "title", "N/A")
        ai_meta = getattr(result, "ai_metadata", None)
        if ai_meta:
            logger.info(
                "Classified: %s | Score: %.2f | Decision: %s",
                title,
                ai_meta.ai_confidence_score,
                ai_meta.decision,
            )

        return result

    def get_metrics(self) -> dict:
        """Возвращает метрики для мониторинга."""
        return {
            "total_calls": self._total_calls,
            "cache_hit_rate": self._cache_hits / max(self._total_calls, 1),
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "estimated_cost_usd": (
                self._total_input_tokens / 1_000_000 * 0.014
                + self._total_output_tokens / 1_000_000 * 0.28
            ),
        }


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers that LLMs sometimes produce."""
    if not text.startswith("```"):
        return text
    text = _MD_FENCE_RE.sub("", text, count=1)
    if text.endswith("```"):
        text = text[: -len("```")]
    return text.strip()
