"""CLI for source-grounded quiz generation."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from typing import Sequence

from src.ai.client import AiGenerationError, AiQuotaUnavailable, GroqQuizAiClient
from src.ai.schemas import CATEGORIES, DIFFICULTIES
from src.comic_vine_client import (
    ComicVineClient,
    ComicVineError,
    ComicVineQuotaUnavailable,
)
from src.config import ConfigurationError, MAX_GENERATION_COUNT, Settings
from src.firebase_client import (
    FirebaseInitializationError,
    QuizFirestoreRepository,
    initialize_firestore,
)
from src.quiz_generator import QuizGenerationError, generate_quiz_questions
from src.web.research_client import TavilyResearchClient, WebResearchError


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gera perguntas verificáveis para o Marvel Multiverse."
    )
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument(
        "--difficulty", choices=sorted([*DIFFICULTIES, "MIXED"]), default="MIXED"
    )
    parser.add_argument(
        "--category", choices=sorted([*CATEGORIES, "MIXED"]), default="MIXED"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-web", action="store_true")
    parser.add_argument("--source", choices=("comicvine", "mixed"), default="comicvine")
    parser.add_argument("--model", help="sobrescreve AI_MODEL somente nesta execução")
    return parser


def _configure_console() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8")
            except OSError:
                pass


def main(argv: Sequence[str] | None = None) -> int:
    _configure_console()
    args = build_parser().parse_args(argv)
    if not 1 <= args.count <= MAX_GENERATION_COUNT:
        LOGGER.error("[ERROR] --count deve estar entre 1 e %s", MAX_GENERATION_COUNT)
        return 2
    use_web = args.source == "mixed" and not args.no_web
    try:
        settings = Settings.from_environment()
        if args.model:
            settings = replace(settings, ai_model=args.model.strip())
        settings.validate_for_run(use_web=use_web)
        db = initialize_firestore(settings)
        repository = QuizFirestoreRepository(db)
        context_client = ComicVineClient(
            settings.comic_vine_api_key,
            user_agent=settings.comic_vine_user_agent,
            page_size=settings.comic_vine_page_size,
            max_pages=settings.comic_vine_max_pages,
            request_interval=settings.comic_vine_request_interval,
        )
        ai_client = GroqQuizAiClient(
            settings.ai_api_key, settings.ai_model,
            max_retries=settings.ai_max_retries,
        )
        web_client = None
        if use_web and settings.web_search_provider == "tavily":
            web_client = TavilyResearchClient(
                settings.web_search_api_key,
                settings.web_trusted_domains,
                max_results=settings.web_max_results,
            )

        LOGGER.info("Marvel Multiverse — Quiz Generator\n")
        LOGGER.info("Solicitado: %s perguntas", args.count)
        LOGGER.info("Categoria: %s", args.category)
        LOGGER.info("Dificuldade: %s", args.difficulty)
        LOGGER.info("Modelo: %s/%s", settings.ai_provider, settings.ai_model)
        LOGGER.info("Web: %s\n", "ativada" if web_client else "desativada")
        summary = generate_quiz_questions(
            count=args.count,
            difficulty=args.difficulty,
            category=args.category,
            dry_run=args.dry_run,
            context_client=context_client,
            ai_client=ai_client,
            repository=repository,
            ai_batch_size=settings.ai_batch_size,
            web_client=web_client,
        )
    except (AiQuotaUnavailable, ComicVineQuotaUnavailable) as error:
        LOGGER.warning("[WARN] Geração ignorada: %s", error)
        LOGGER.warning("Nenhuma alteração foi feita no Firestore.")
        return 0
    except (
        ConfigurationError, FirebaseInitializationError, ComicVineError,
        AiGenerationError, WebResearchError, QuizGenerationError,
    ) as error:
        LOGGER.error("[ERROR] %s", error)
        return 1

    LOGGER.info("\n---------------------------------")
    LOGGER.info("Solicitadas: %s", summary.requested)
    LOGGER.info("Contextos obtidos: %s", summary.contexts)
    LOGGER.info("Geradas pela IA: %s", summary.generated_by_ai)
    LOGGER.info("Válidas: %s", len(summary.valid))
    LOGGER.info("Duplicadas: %s", summary.duplicates)
    LOGGER.info("Inválidas: %s", summary.invalid)
    LOGGER.info("Inseridas no Firestore: %s", summary.inserted)
    if summary.dry_run:
        LOGGER.info("Dry-run concluído; Firestore não foi alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
