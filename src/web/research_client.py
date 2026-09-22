"""Optional Tavily enrichment restricted to configured trusted domains."""

from __future__ import annotations

import re
from typing import Any, Sequence
from urllib.parse import urlparse

from src.comic_vine_client import SourceContext


class WebResearchError(RuntimeError):
    """Optional web enrichment failed."""


class TavilyResearchClient:
    endpoint = "https://api.tavily.com/search"

    def __init__(
        self,
        api_key: str,
        trusted_domains: Sequence[str],
        *,
        max_results: int = 5,
        timeout: float = 30.0,
        session: Any | None = None,
    ) -> None:
        if not api_key:
            raise WebResearchError("chave Tavily ausente")
        if session is None:
            try:
                import requests
            except ImportError as error:
                raise WebResearchError("requests não está instalado") from error
            session = requests.Session()
        self.api_key = api_key
        self.trusted_domains = tuple(domain.casefold() for domain in trusted_domains)
        self.max_results = max_results
        self.timeout = timeout
        self.session = session

    def _trusted(self, url: str) -> bool:
        hostname = (urlparse(url).hostname or "").casefold()
        return any(hostname == domain or hostname.endswith(f".{domain}") for domain in self.trusted_domains)

    def enrich(self, contexts: Sequence[SourceContext]) -> list[SourceContext]:
        titles = [context.title for context in contexts[:6]]
        if not titles:
            return []
        query = "Marvel " + " OR ".join(f'"{title}"' for title in titles)
        try:
            response = self.session.post(
                self.endpoint,
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": self.max_results,
                    "include_domains": list(self.trusted_domains),
                    "include_answer": False,
                    "include_raw_content": False,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            raise WebResearchError(
                f"pesquisa web falhou ({type(error).__name__})"
            ) from error
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise WebResearchError("Tavily retornou payload inesperado")

        evidence: list[SourceContext] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            title = item.get("title")
            content = item.get("content")
            if not all(isinstance(value, str) and value.strip() for value in (url, title, content)):
                continue
            if not self._trusted(url):
                continue
            clean_content = re.sub(r"\s+", " ", content).strip()[:3000]
            evidence.append(SourceContext(
                source_type="WEB", reference=url, title=title.strip(),
                category="GENERAL", content=clean_content,
            ))
        return evidence
