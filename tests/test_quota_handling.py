from __future__ import annotations

import unittest
from unittest.mock import patch

from src.ai.client import (
    AiQuotaUnavailable,
    GroqQuizAiClient,
    _is_quota_error,
    _split_api_keys,
)
from src.main import main


class StatusError(RuntimeError):
    status_code = 429


class FailingStructuredModel:
    def invoke(self, messages):
        raise StatusError("provider temporarily unavailable")


class SuccessfulStructuredModel:
    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return {
            "questions": [{
                "question": "Quem é Peter Parker?",
                "alternatives": ["Spider-Man", "Thor", "Hulk", "Loki"],
                "correctAnswerIndex": 0,
                "difficulty": "EASY",
                "category": "CHARACTERS",
                "coinVerseReward": 25,
                "sourceReferences": ["comicvine:character:1443"],
                "supportingFact": "Peter Parker é o Spider-Man.",
            }]
        }


class QuotaHandlingTests(unittest.TestCase):
    def test_splits_deduplicates_and_preserves_api_key_order(self):
        self.assertEqual(_split_api_keys(" first | second || first "), ("first", "second"))

    def test_recognizes_http_429_and_quota_messages(self):
        self.assertTrue(_is_quota_error(StatusError("limited")))
        self.assertTrue(_is_quota_error(RuntimeError("insufficient_quota")))
        self.assertFalse(_is_quota_error(RuntimeError("invalid schema")))

    def test_ai_client_uses_next_key_on_quota_and_remembers_success(self):
        client = GroqQuizAiClient.__new__(GroqQuizAiClient)
        successful = SuccessfulStructuredModel()
        client._structured_models = [FailingStructuredModel(), successful]
        client._max_retries = 3
        client._active_key_index = 0

        first = client.generate(
            count=1, difficulty="EASY", category="CHARACTERS", context="data"
        )
        second = client.generate(
            count=1, difficulty="EASY", category="CHARACTERS", context="data"
        )
        self.assertEqual(len(first.questions), 1)
        self.assertEqual(len(second.questions), 1)
        self.assertEqual(successful.calls, 2)
        self.assertEqual(client._active_key_index, 1)

    def test_ai_client_reports_quota_after_all_keys_fail(self):
        client = GroqQuizAiClient.__new__(GroqQuizAiClient)
        client._structured_models = [FailingStructuredModel(), FailingStructuredModel()]
        client._max_retries = 3
        client._active_key_index = 0
        with self.assertRaises(AiQuotaUnavailable):
            client.generate(
                count=1, difficulty="EASY", category="CHARACTERS", context="data"
            )

    def test_cli_returns_success_when_quota_is_unavailable(self):
        with patch(
            "src.main.Settings.from_environment",
            side_effect=AiQuotaUnavailable("cota esgotada"),
        ):
            exit_code = main(["--count", "1"])
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
