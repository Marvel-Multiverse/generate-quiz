from __future__ import annotations

import unittest
from unittest.mock import patch

from src.ai.schemas import GeneratedQuizBatch, GeneratedQuizQuestion
from src.comic_vine_client import SourceContext
from src.firebase_client import QuizFirestoreRepository
from src.quiz_generator import generate_quiz_questions


def generated(prompt, answer, alternatives, supporting):
    return GeneratedQuizQuestion(
        question=prompt,
        alternatives=alternatives,
        correctAnswerIndex=alternatives.index(answer),
        difficulty="EASY",
        category="CHARACTERS",
        coinVerseReward=25,
        sourceReferences=["comicvine:character:1443"],
        supportingFact=supporting,
    )


class FakeContextClient:
    def fetch_contexts(self, category, limit):
        return [SourceContext(
            "COMIC_VINE", "comicvine:character:1443", "Spider-Man", "CHARACTERS",
            '{"name":"Spider-Man","real_name":"Peter Parker","publisher":"Marvel","aliases":"Wall-Crawler"}',
        )]


class FakeAiClient:
    def generate(self, **kwargs):
        return GeneratedQuizBatch(questions=[
            generated(
                "Qual é o nome verdadeiro do Homem-Aranha?", "Peter Parker",
                ["Peter Parker", "Tony Stark", "Steve Rogers", "Bruce Banner"],
                "real_name Peter Parker",
            ),
            generated(
                "Qual alias aparece associado ao Spider-Man na fonte?", "Wall-Crawler",
                ["Wall-Crawler", "Web-Knight", "Iron Spider", "Arachnid King"],
                "aliases Wall-Crawler",
            ),
        ])


class FakeRepository:
    def __init__(self):
        self.insert_calls = []

    def fetch_existing_questions(self):
        return []

    def insert_questions(self, questions):
        self.insert_calls.append(list(questions))
        return len(questions)


class FakeSnapshot:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class FakeCollection:
    def __init__(self):
        self.documents = []

    def select(self, fields):
        return self

    def stream(self):
        return iter([FakeSnapshot({"question": "Existing?"})])

    def document(self):
        reference = f"new_{len(self.documents)}"
        self.documents.append(reference)
        return reference


class FakeBatch:
    def __init__(self):
        self.sets = []
        self.committed = False

    def set(self, reference, payload):
        self.sets.append((reference, payload))

    def commit(self):
        self.committed = True


class FakeDatabase:
    def __init__(self):
        self.quiz = FakeCollection()
        self.last_batch = None

    def collection(self, name):
        assert name == "quiz"
        return self.quiz

    def batch(self):
        self.last_batch = FakeBatch()
        return self.last_batch


class PipelineAndFirebaseTests(unittest.TestCase):
    def test_dry_run_uses_mocked_sources_and_llm_without_inserting(self):
        repository = FakeRepository()
        summary = generate_quiz_questions(
            count=2, difficulty="EASY", category="CHARACTERS", dry_run=True,
            context_client=FakeContextClient(), ai_client=FakeAiClient(),
            repository=repository, ai_batch_size=2,
        )
        self.assertEqual(len(summary.valid), 2)
        self.assertEqual(summary.inserted, 0)
        self.assertEqual(repository.insert_calls, [])

    def test_firestore_payload_is_admin_only_and_daily_inactive(self):
        database = FakeDatabase()
        repository = QuizFirestoreRepository(database)
        item = generated(
            "Qual é o nome verdadeiro do Homem-Aranha?", "Peter Parker",
            ["Peter Parker", "Tony Stark", "Steve Rogers", "Bruce Banner"],
            "real_name Peter Parker",
        )
        with patch("firebase_admin.firestore.SERVER_TIMESTAMP", "SERVER_TIMESTAMP"):
            inserted = repository.insert_questions([item])
        self.assertEqual(inserted, 1)
        self.assertTrue(database.last_batch.committed)
        payload = database.last_batch.sets[0][1]
        self.assertFalse(payload["isDailyQuiz"])
        self.assertIsNone(payload["dailyQuizDate"])
        self.assertTrue(payload["generatedByAi"])
        self.assertTrue(payload["verified"])
        self.assertNotIn("supportingFact", payload)
        self.assertEqual(payload["createdAt"], "SERVER_TIMESTAMP")


if __name__ == "__main__":
    unittest.main()
