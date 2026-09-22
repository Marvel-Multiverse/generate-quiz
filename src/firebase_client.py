"""Firebase initialization and the quiz-only Firestore repository."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Sequence

from src.ai.schemas import GeneratedQuizQuestion
from src.config import Settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CREDENTIALS_PATH = PROJECT_ROOT / "firebase-service-account.json"
FIREBASE_APP_NAME = "marvel-multiverse-generate-quiz"


class FirebaseInitializationError(RuntimeError):
    """Firebase could not be initialized safely."""


def _credential_source() -> Any:
    try:
        from firebase_admin import credentials
    except ImportError as error:
        raise FirebaseInitializationError("firebase-admin não está instalado") from error
    credential_variable = "FIREBASE_SERVICE_ACCOUNT_JSON"
    raw_json = os.getenv(credential_variable, "").strip()
    if not raw_json:
        credential_variable = "FIREBASE_SERVICE_ACCOUNT"
        raw_json = os.getenv(credential_variable, "").strip()
    if raw_json:
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as error:
            raise FirebaseInitializationError(
                f"{credential_variable} não contém JSON válido"
            ) from error
        if not isinstance(payload, dict) or payload.get("type") != "service_account":
            raise FirebaseInitializationError(
                f"{credential_variable} não contém uma Service Account válida"
            )
        return credentials.Certificate(payload)
    configured = os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()
    path = Path(configured).expanduser() if configured else DEFAULT_CREDENTIALS_PATH
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not path.is_file():
        raise FirebaseInitializationError(
            "credenciais Firebase não encontradas; defina "
            "FIREBASE_SERVICE_ACCOUNT_JSON ou FIREBASE_CREDENTIALS_PATH"
        )
    return credentials.Certificate(str(path))


def initialize_firestore(settings: Settings) -> Any:
    try:
        import firebase_admin
        from firebase_admin import firestore
    except ImportError as error:
        raise FirebaseInitializationError("firebase-admin não está instalado") from error
    try:
        try:
            app = firebase_admin.get_app(FIREBASE_APP_NAME)
        except ValueError:
            app = firebase_admin.initialize_app(
                _credential_source(), name=FIREBASE_APP_NAME
            )
        return firestore.client(app=app, database_id=settings.firebase_database_id)
    except FirebaseInitializationError:
        raise
    except Exception as error:
        raise FirebaseInitializationError(
            f"falha ao inicializar Firebase ({type(error).__name__})"
        ) from error


class QuizFirestoreRepository:
    def __init__(self, db: Any) -> None:
        self.db = db
        self.collection = db.collection("quiz")

    def fetch_existing_questions(self) -> list[str]:
        try:
            snapshots = self.collection.select(["question"]).stream()
            return [
                question.strip()
                for snapshot in snapshots
                if isinstance((question := (snapshot.to_dict() or {}).get("question")), str)
                and question.strip()
            ]
        except Exception as error:
            raise FirebaseInitializationError(
                f"falha ao consultar perguntas existentes ({type(error).__name__})"
            ) from error

    def insert_questions(self, questions: Sequence[GeneratedQuizQuestion]) -> int:
        if len(questions) > 200:
            raise FirebaseInitializationError(
                "uma execução aceita no máximo 200 inserts atômicos"
            )
        try:
            from firebase_admin import firestore

            batch = self.db.batch()
            for question in questions:
                reference = self.collection.document()
                source_kinds = {
                    "WEB" if ref.startswith(("https://", "http://")) else "COMIC_VINE"
                    for ref in question.sourceReferences
                }
                source_type = next(iter(source_kinds)) if len(source_kinds) == 1 else "MIXED"
                payload = question.model_dump(exclude={"supportingFact"})
                payload.update({
                    "sourceType": source_type,
                    "generatedByAi": True,
                    "generatedAt": firestore.SERVER_TIMESTAMP,
                    "verified": True,
                    "isDailyQuiz": False,
                    "dailyQuizDate": None,
                    "createdAt": firestore.SERVER_TIMESTAMP,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                })
                batch.set(reference, payload)
            batch.commit()
            return len(questions)
        except FirebaseInitializationError:
            raise
        except Exception as error:
            raise FirebaseInitializationError(
                f"falha ao inserir perguntas ({type(error).__name__})"
            ) from error
