"""LangChain/Groq adapter with bounded retries and Pydantic output."""

from __future__ import annotations

import logging
import time
from typing import Protocol

from src.ai.prompts import SYSTEM_PROMPT, build_generation_prompt
from src.ai.schemas import GeneratedQuizBatch


LOGGER = logging.getLogger(__name__)


class AiGenerationError(RuntimeError):
    """The model failed after bounded retries."""


class AiQuotaUnavailable(AiGenerationError):
    """The provider temporarily cannot serve the request because quota is exhausted."""


def _is_quota_error(error: Exception) -> bool:
    """Recognize common Groq/LangChain quota and rate-limit error shapes safely."""
    current: BaseException | None = error
    visited: set[int] = set()
    quota_markers = (
        "insufficient_quota",
        "rate_limit_exceeded",
        "rate limit",
        "rate_limit",
        "quota exceeded",
        "quota_exceeded",
        "token quota",
        "tokens per minute",
        "tokens per day",
        "requests per minute",
        "credits exhausted",
        "insufficient credits",
        "billing limit",
    )
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        status_code = getattr(current, "status_code", None)
        response = getattr(current, "response", None)
        response_status = getattr(response, "status_code", None)
        if status_code == 429 or response_status == 429:
            return True
        message = str(current).casefold()
        if any(marker in message for marker in quota_markers):
            return True
        current = current.__cause__ or current.__context__
    return False


class QuizAiClient(Protocol):
    def generate(
        self, *, count: int, difficulty: str, category: str, context: str
    ) -> GeneratedQuizBatch: ...


class GroqQuizAiClient:
    def __init__(self, api_key: str, model: str, *, max_retries: int = 3) -> None:
        if not api_key:
            raise AiGenerationError("chave da Groq ausente")
        try:
            from langchain_groq import ChatGroq
        except ImportError as error:
            raise AiGenerationError(
                "langchain-groq não está instalado; execute pip install -r requirements.txt"
            ) from error
        llm = ChatGroq(
            model=model,
            temperature=0.2,
            api_key=api_key,
            max_retries=0,
        )
        self._structured = llm.with_structured_output(
            GeneratedQuizBatch, method="json_schema"
        )
        self._max_retries = max_retries

    def generate(
        self, *, count: int, difficulty: str, category: str, context: str
    ) -> GeneratedQuizBatch:
        prompt = build_generation_prompt(
            count=count, difficulty=difficulty, category=category, context=context
        )
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                result = self._structured.invoke([
                    ("system", SYSTEM_PROMPT),
                    ("human", prompt),
                ])
                if isinstance(result, GeneratedQuizBatch):
                    return result
                return GeneratedQuizBatch.model_validate(result)
            except Exception as error:
                if _is_quota_error(error):
                    raise AiQuotaUnavailable(
                        "cota da Groq indisponível ou esgotada; nenhuma pergunta foi inserida"
                    ) from error
                last_error = error
                if attempt < self._max_retries:
                    wait_seconds = min(2 ** (attempt - 1), 4)
                    LOGGER.warning(
                        "[RETRY] IA tentativa %s/%s em %ss (%s)",
                        attempt + 1, self._max_retries, wait_seconds,
                        type(error).__name__,
                    )
                    time.sleep(wait_seconds)
        raise AiGenerationError(
            f"a IA falhou após {self._max_retries} tentativas ({type(last_error).__name__})"
        ) from last_error
