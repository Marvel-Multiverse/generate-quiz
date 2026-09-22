from __future__ import annotations

import os
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from src.firebase_client import FirebaseInitializationError, _credential_source


def fake_firebase_admin() -> ModuleType:
    module = ModuleType("firebase_admin")
    module.credentials = SimpleNamespace(Certificate=lambda value: value)
    return module


class FirebaseCredentialTests(unittest.TestCase):
    def test_prefers_standard_json_secret_and_accepts_legacy_alias(self):
        standard = '{"type":"service_account","project_id":"standard"}'
        legacy = '{"type":"service_account","project_id":"legacy"}'
        with patch.dict(sys.modules, {"firebase_admin": fake_firebase_admin()}):
            with patch.dict(
                os.environ,
                {
                    "FIREBASE_SERVICE_ACCOUNT_JSON": standard,
                    "FIREBASE_SERVICE_ACCOUNT": legacy,
                },
                clear=True,
            ):
                self.assertEqual(_credential_source()["project_id"], "standard")
            with patch.dict(
                os.environ, {"FIREBASE_SERVICE_ACCOUNT": legacy}, clear=True
            ):
                self.assertEqual(_credential_source()["project_id"], "legacy")

    def test_rejects_non_service_account_json(self):
        with patch.dict(sys.modules, {"firebase_admin": fake_firebase_admin()}):
            with patch.dict(
                os.environ, {"FIREBASE_SERVICE_ACCOUNT_JSON": "{}"}, clear=True
            ):
                with self.assertRaisesRegex(
                    FirebaseInitializationError, "Service Account válida"
                ):
                    _credential_source()


if __name__ == "__main__":
    unittest.main()
