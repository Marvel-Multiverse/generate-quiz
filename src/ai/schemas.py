"""Strict Pydantic contracts for model output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


DIFFICULTIES = {"EASY", "MEDIUM", "HARD"}
CATEGORIES = {
    "CHARACTERS", "POWERS", "TEAMS", "COMICS", "STORY_ARCS", "MOVIES",
    "LOCATIONS", "GENERAL",
}
CATEGORY_ALIASES = {
    "CHARACTER": "CHARACTERS", "HERO": "CHARACTERS", "HEROES": "CHARACTERS",
    "POWER": "POWERS", "TEAM": "TEAMS", "COMIC": "COMICS",
    "STORY_ARC": "STORY_ARCS", "ARC": "STORY_ARCS", "MOVIE": "MOVIES",
    "LOCATION": "LOCATIONS",
}


class GeneratedQuizQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=8, max_length=500)
    alternatives: list[str] = Field(min_length=4, max_length=6)
    correctAnswerIndex: int
    difficulty: str
    category: str
    coinVerseReward: int
    sourceReferences: list[str] = Field(min_length=1, max_length=8)
    supportingFact: str = Field(min_length=3, max_length=1000)

    @field_validator("difficulty", mode="before")
    @classmethod
    def normalize_difficulty(cls, value: Any) -> str:
        normalized = str(value).strip().upper()
        if normalized not in DIFFICULTIES:
            raise ValueError("difficulty deve ser EASY, MEDIUM ou HARD")
        return normalized

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: Any) -> str:
        normalized = str(value).strip().upper().replace(" ", "_").replace("-", "_")
        normalized = CATEGORY_ALIASES.get(normalized, normalized)
        if normalized not in CATEGORIES:
            raise ValueError("category não pertence ao contrato oficial")
        return normalized


class GeneratedQuizBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[GeneratedQuizQuestion] = Field(min_length=1, max_length=20)
