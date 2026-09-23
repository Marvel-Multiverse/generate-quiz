"""Source -> LLM -> validation -> deduplication -> Firestore pipeline."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from src.ai.client import QuizAiClient
from src.ai.schemas import GeneratedQuizQuestion
from src.comic_vine_client import (
    SourceContext,
    select_contexts_for_prompt,
    serialize_contexts,
)
from src.duplicate_detector import DuplicateDetector
from src.quiz_validator import validate_question


LOGGER = logging.getLogger(__name__)


class QuizGenerationError(RuntimeError):
    """The generation pipeline could not safely meet its target."""


class ContextClient(Protocol):
    def fetch_contexts(self, category: str, limit: int) -> list[SourceContext]: ...


class WebClient(Protocol):
    def enrich(self, contexts: Sequence[SourceContext]) -> list[SourceContext]: ...


class QuizRepository(Protocol):
    def fetch_existing_questions(self) -> list[str]: ...
    def insert_questions(self, questions: Sequence[GeneratedQuizQuestion]) -> int: ...


@dataclass(frozen=True)
class GenerationSummary:
    requested: int
    contexts: int
    generated_by_ai: int
    valid: tuple[GeneratedQuizQuestion, ...]
    duplicates: int
    invalid: int
    inserted: int
    dry_run: bool


def generate_quiz_questions(
    *,
    count: int,
    difficulty: str,
    category: str,
    dry_run: bool,
    context_client: ContextClient,
    ai_client: QuizAiClient,
    repository: QuizRepository,
    ai_batch_size: int = 10,
    ai_context_max_chars: int = 18_000,
    web_client: WebClient | None = None,
) -> GenerationSummary:
    if count <= 0 or count > 200:
        raise QuizGenerationError("count deve estar entre 1 e 200")
    context_limit = min(100, max(12, count * 2))
    contexts = context_client.fetch_contexts(category, context_limit)
    if not contexts:
        raise QuizGenerationError("Comic Vine não retornou contexto Marvel suficiente")
    if web_client is not None:
        try:
            web_contexts = web_client.enrich(contexts)
            contexts = [*contexts, *web_contexts]
            LOGGER.info("Contextos web confiáveis adicionados: %s", len(web_contexts))
        except Exception as error:
            LOGGER.warning(
                "[WARN] Web opcional indisponível; continuando com Comic Vine (%s)",
                type(error).__name__,
            )

    supplied_contexts = select_contexts_for_prompt(
        contexts, max_chars=ai_context_max_chars
    )
    serialized = serialize_contexts(supplied_contexts)
    if not serialized:
        raise QuizGenerationError("contexto serializado vazio")
    existing = repository.fetch_existing_questions()
    duplicate_detector = DuplicateDetector(existing)
    accepted: list[GeneratedQuizQuestion] = []
    generated_total = 0
    duplicate_total = 0
    invalid_total = 0
    max_calls = max(2, math.ceil(count / ai_batch_size) * 2)

    for _ in range(max_calls):
        if len(accepted) >= count:
            break
        remaining = count - len(accepted)
        requested = min(ai_batch_size, max(remaining, min(ai_batch_size, remaining * 2)))
        batch = ai_client.generate(
            count=requested,
            difficulty=difficulty,
            category=category,
            context=serialized,
        )
        generated_total += len(batch.questions)
        for generated in batch.questions:
            if len(accepted) >= count:
                break
            validation = validate_question(
                generated, supplied_contexts,
                requested_difficulty=difficulty,
                requested_category=category,
            )
            if not validation.valid or validation.question is None:
                invalid_total += 1
                LOGGER.info("[INVALID] %s — %s", generated.question, validation.reason)
                continue
            if duplicate_detector.is_duplicate(validation.question.question):
                duplicate_total += 1
                LOGGER.info("[DUPLICATE] %s", validation.question.question)
                continue
            accepted.append(validation.question)
            duplicate_detector.add(validation.question.question)
            LOGGER.info("[VALID] %s", validation.question.question)

    if len(accepted) < count:
        raise QuizGenerationError(
            f"apenas {len(accepted)}/{count} perguntas passaram pela validação após "
            f"{max_calls} chamadas limitadas à IA"
        )
    inserted = 0 if dry_run else repository.insert_questions(accepted)
    return GenerationSummary(
        requested=count,
        contexts=len(supplied_contexts),
        generated_by_ai=generated_total,
        valid=tuple(accepted),
        duplicates=duplicate_total,
        invalid=invalid_total,
        inserted=inserted,
        dry_run=dry_run,
    )
