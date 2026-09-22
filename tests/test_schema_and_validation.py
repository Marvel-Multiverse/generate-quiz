from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.ai.schemas import GeneratedQuizQuestion
from src.comic_vine_client import SourceContext
from src.quiz_validator import validate_question


def question(**overrides):
    payload = {
        "question": "Qual é o nome verdadeiro do Homem-Aranha?",
        "alternatives": ["Peter Parker", "Tony Stark", "Steve Rogers", "Bruce Banner"],
        "correctAnswerIndex": 0,
        "difficulty": "easy",
        "category": "character",
        "coinVerseReward": 999,
        "sourceReferences": ["comicvine:character:1443"],
        "supportingFact": "real_name Peter Parker",
    }
    payload.update(overrides)
    return GeneratedQuizQuestion.model_validate(payload)


def context(content='{"name":"Spider-Man","real_name":"Peter Parker"}'):
    return SourceContext(
        "COMIC_VINE", "comicvine:character:1443", "Spider-Man", "CHARACTERS", content
    )


class SchemaAndValidationTests(unittest.TestCase):
    def test_schema_requires_at_least_four_alternatives(self):
        with self.assertRaises(ValidationError):
            question(alternatives=["A", "B", "C"])

    def test_schema_normalizes_official_values(self):
        generated = question()
        self.assertEqual(generated.difficulty, "EASY")
        self.assertEqual(generated.category, "CHARACTERS")

    def test_rejects_invalid_correct_answer_index(self):
        result = validate_question(question(correctAnswerIndex=8), [context()])
        self.assertFalse(result.valid)
        self.assertIn("correctAnswerIndex", result.reason)

    def test_normalizes_reward_from_difficulty(self):
        result = validate_question(question(), [context()])
        self.assertTrue(result.valid)
        self.assertEqual(result.question.coinVerseReward, 25)

    def test_rejects_answer_not_supported_by_referenced_context(self):
        result = validate_question(question(), [context('{"name":"Spider-Man"}')])
        self.assertFalse(result.valid)
        self.assertIn("resposta correta", result.reason)

    def test_rejects_reference_not_supplied_to_model(self):
        result = validate_question(
            question(sourceReferences=["https://example.invalid/fake"]), [context()]
        )
        self.assertFalse(result.valid)

    def test_rejects_requested_category_mismatch(self):
        result = validate_question(
            question(), [context()], requested_category="POWERS"
        )
        self.assertFalse(result.valid)


if __name__ == "__main__":
    unittest.main()
