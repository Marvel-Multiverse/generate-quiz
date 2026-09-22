"""Deterministic validation against source evidence and the Android contract."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Sequence

from src.ai.schemas import GeneratedQuizQuestion
from src.comic_vine_client import SourceContext


REWARDS = {"EASY": 25, "MEDIUM": 50, "HARD": 100}


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold())).strip()


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str
    question: GeneratedQuizQuestion | None = None


def validate_question(
    question: GeneratedQuizQuestion,
    contexts: Sequence[SourceContext],
    *,
    requested_difficulty: str = "MIXED",
    requested_category: str = "MIXED",
) -> ValidationResult:
    prompt = question.question.strip()
    alternatives = [item.strip() for item in question.alternatives]
    if not prompt:
        return ValidationResult(False, "pergunta vazia")
    if len(alternatives) < 4 or any(not item for item in alternatives):
        return ValidationResult(False, "menos de quatro alternativas válidas")
    normalized_alternatives = [normalize_text(item) for item in alternatives]
    if any(not item for item in normalized_alternatives):
        return ValidationResult(False, "alternativa sem conteúdo textual")
    if len(set(normalized_alternatives)) != len(normalized_alternatives):
        return ValidationResult(False, "alternativas duplicadas")
    if not 0 <= question.correctAnswerIndex < len(alternatives):
        return ValidationResult(False, "correctAnswerIndex inválido")
    if requested_difficulty != "MIXED" and question.difficulty != requested_difficulty:
        return ValidationResult(False, "dificuldade diferente da solicitada")
    if requested_category != "MIXED" and question.category != requested_category:
        return ValidationResult(False, "categoria diferente da solicitada")

    contexts_by_reference = {item.reference: item for item in contexts}
    references = list(dict.fromkeys(ref.strip() for ref in question.sourceReferences if ref.strip()))
    if not references or any(ref not in contexts_by_reference for ref in references):
        return ValidationResult(False, "referência ausente ou não fornecida ao modelo")
    referenced_corpus = " ".join(
        f"{contexts_by_reference[ref].title} {contexts_by_reference[ref].content}"
        for ref in references
    )
    normalized_corpus = normalize_text(referenced_corpus)
    correct_answer = normalized_alternatives[question.correctAnswerIndex]
    if correct_answer not in normalized_corpus:
        return ValidationResult(False, "resposta correta não aparece na fonte referenciada")
    supporting_fact = normalize_text(question.supportingFact)
    if not supporting_fact or supporting_fact not in normalized_corpus:
        return ValidationResult(False, "supportingFact não aparece na fonte referenciada")

    normalized = question.model_copy(update={
        "question": prompt,
        "alternatives": alternatives,
        "coinVerseReward": REWARDS[question.difficulty],
        "sourceReferences": references,
        "supportingFact": question.supportingFact.strip(),
    })
    return ValidationResult(True, "ok", normalized)
