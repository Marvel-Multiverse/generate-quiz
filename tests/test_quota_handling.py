from __future__ import annotations

import unittest
from unittest.mock import patch

from src.ai.client import AiQuotaUnavailable, GroqQuizAiClient, _is_quota_error
from src.main import main


class StatusError(RuntimeError):
    status_code = 429


class FailingStructuredModel:
    def invoke(self, messages):
        raise StatusError("provider temporarily unavailable")


class QuotaHandlingTests(unittest.TestCase):
    def test_recognizes_http_429_and_quota_messages(self):
        self.assertTrue(_is_quota_error(StatusError("limited")))
        self.assertTrue(_is_quota_error(RuntimeError("insufficient_quota")))
        self.assertFalse(_is_quota_error(RuntimeError("invalid schema")))

    def test_ai_client_stops_immediately_on_quota(self):
        client = GroqQuizAiClient.__new__(GroqQuizAiClient)
        client._structured = FailingStructuredModel()
        client._max_retries = 3
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
