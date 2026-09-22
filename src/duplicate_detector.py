"""Lightweight textual near-duplicate detection without an embedding service."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable

from src.quiz_validator import normalize_text


STOPWORDS = {
    "a", "ao", "aos", "as", "da", "das", "de", "do", "dos", "e", "em",
    "e", "qual", "que", "o", "os", "um", "uma",
}


def canonical_question(value: str) -> str:
    tokens = [token for token in normalize_text(value).split() if token not in STOPWORDS]
    return " ".join(tokens)


def _token_similarity(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


class DuplicateDetector:
    def __init__(
        self,
        existing_questions: Iterable[str] = (),
        *,
        sequence_threshold: float = 0.84,
        token_threshold: float = 0.80,
    ) -> None:
        self.sequence_threshold = sequence_threshold
        self.token_threshold = token_threshold
        self._questions = [
            canonical for item in existing_questions
            if (canonical := canonical_question(item))
        ]

    def is_duplicate(self, question: str) -> bool:
        candidate = canonical_question(question)
        if not candidate:
            return True
        for existing in self._questions:
            if candidate == existing:
                return True
            if SequenceMatcher(None, candidate, existing).ratio() >= self.sequence_threshold:
                return True
            if _token_similarity(candidate, existing) >= self.token_threshold:
                return True
        return False

    def add(self, question: str) -> None:
        canonical = canonical_question(question)
        if canonical:
            self._questions.append(canonical)
