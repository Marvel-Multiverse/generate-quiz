"""Central configuration for the quiz generator."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_GENERATION_COUNT = 200


class ConfigurationError(ValueError):
    """Raised when configuration is missing or invalid."""


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name} deve ser um número inteiro") from error
    if value <= 0:
        raise ConfigurationError(f"{name} deve ser maior que zero")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name} deve ser um número") from error
    if value <= 0:
        raise ConfigurationError(f"{name} deve ser maior que zero")
    return value


@dataclass(frozen=True)
class Settings:
    firebase_database_id: str
    timezone: str
    comic_vine_api_key: str = field(repr=False)
    comic_vine_user_agent: str
    comic_vine_page_size: int
    comic_vine_max_pages: int
    comic_vine_request_interval: float
    ai_provider: str
    ai_model: str
    ai_api_key: str = field(repr=False)
    ai_batch_size: int
    ai_max_retries: int
    ai_context_max_chars: int
    web_search_provider: str
    web_search_api_key: str = field(repr=False)
    web_trusted_domains: tuple[str, ...]
    web_max_results: int

    @classmethod
    def from_environment(cls) -> "Settings":
        try:
            from dotenv import load_dotenv

            load_dotenv(PROJECT_ROOT / ".env", override=False)
        except ImportError:
            pass

        database_id = os.getenv("FIRESTORE_DATABASE_ID", "default").strip()
        if not database_id or "/" in database_id:
            raise ConfigurationError(
                "FIRESTORE_DATABASE_ID deve conter somente o ID do banco"
            )
        timezone = os.getenv("APP_TIMEZONE", "America/Sao_Paulo").strip()
        if not timezone:
            raise ConfigurationError("APP_TIMEZONE não pode ficar vazio")
        provider = os.getenv("AI_PROVIDER", "groq").strip().casefold()
        if provider != "groq":
            raise ConfigurationError("AI_PROVIDER suportado nesta versão: groq")
        web_provider = os.getenv("WEB_SEARCH_PROVIDER", "none").strip().casefold()
        if web_provider not in {"none", "tavily"}:
            raise ConfigurationError("WEB_SEARCH_PROVIDER deve ser none ou tavily")
        domains = tuple(
            domain.strip().casefold()
            for domain in os.getenv("WEB_TRUSTED_DOMAINS", "marvel.com").split(",")
            if domain.strip()
        )
        return cls(
            firebase_database_id=database_id,
            timezone=timezone,
            comic_vine_api_key=os.getenv("COMIC_VINE_API_KEY", "").strip(),
            comic_vine_user_agent=os.getenv(
                "COMIC_VINE_USER_AGENT", "MarvelMultiverseQuizGenerator/1.0"
            ).strip(),
            comic_vine_page_size=min(_positive_int("COMIC_VINE_PAGE_SIZE", 100), 100),
            comic_vine_max_pages=_positive_int("COMIC_VINE_MAX_PAGES", 3),
            comic_vine_request_interval=_positive_float(
                "COMIC_VINE_REQUEST_INTERVAL", 1.1
            ),
            ai_provider=provider,
            ai_model=os.getenv("AI_MODEL", "openai/gpt-oss-120b").strip(),
            ai_api_key=(
                os.getenv("GROQ_API_KEY", "").strip()
                or os.getenv("AI_API_KEY", "").strip()
            ),
            ai_batch_size=min(_positive_int("AI_BATCH_SIZE", 10), 20),
            ai_max_retries=min(_positive_int("AI_MAX_RETRIES", 3), 5),
            ai_context_max_chars=min(
                max(_positive_int("AI_CONTEXT_MAX_CHARS", 18_000), 2_000),
                60_000,
            ),
            web_search_provider=web_provider,
            web_search_api_key=(
                os.getenv("WEB_SEARCH_API_KEY", "").strip()
                or os.getenv("TAVILY_API_KEY", "").strip()
            ),
            web_trusted_domains=domains,
            web_max_results=min(_positive_int("WEB_MAX_RESULTS", 5), 10),
        )

    def validate_for_run(self, *, use_web: bool) -> None:
        if not self.comic_vine_api_key:
            raise ConfigurationError("COMIC_VINE_API_KEY não está configurada")
        if not self.ai_model:
            raise ConfigurationError("AI_MODEL não pode ficar vazio")
        if not self.ai_api_key:
            raise ConfigurationError("GROQ_API_KEY (ou AI_API_KEY) não está configurada")
        if use_web and self.web_search_provider == "tavily" and not self.web_search_api_key:
            raise ConfigurationError(
                "WEB_SEARCH_API_KEY (ou TAVILY_API_KEY) é necessária para Tavily"
            )
