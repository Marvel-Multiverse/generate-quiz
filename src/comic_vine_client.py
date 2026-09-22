"""Rate-conscious Comic Vine context collector."""

from __future__ import annotations

import html
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


LOGGER = logging.getLogger(__name__)
BASE_URL = "https://comicvine.gamespot.com/api"
MARVEL_PUBLISHER_ID = 31
MARVEL_NAMES = {"marvel", "marvel comics", "marvel entertainment", "marvel studios"}


RESOURCE_SPECS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "CHARACTERS": (
        "characters",
        ("id", "name", "real_name", "aliases", "deck", "description", "publisher", "powers", "teams", "api_detail_url", "site_detail_url"),
        "character",
    ),
    # Powers are collected through Marvel characters so every fact remains publisher-scoped.
    "POWERS": (
        "characters",
        ("id", "name", "real_name", "deck", "publisher", "powers", "api_detail_url", "site_detail_url"),
        "character",
    ),
    "TEAMS": (
        "teams",
        ("id", "name", "aliases", "deck", "description", "publisher", "characters", "api_detail_url", "site_detail_url"),
        "team",
    ),
    "COMICS": (
        "volumes",
        ("id", "name", "deck", "description", "publisher", "start_year", "count_of_issues", "issues", "api_detail_url", "site_detail_url"),
        "volume",
    ),
    "STORY_ARCS": (
        "story_arcs",
        ("id", "name", "deck", "description", "publisher", "issues", "api_detail_url", "site_detail_url"),
        "story_arc",
    ),
    "MOVIES": (
        "movies",
        ("id", "name", "deck", "description", "release_date", "characters", "studios", "api_detail_url", "site_detail_url"),
        "movie",
    ),
    "LOCATIONS": (
        "locations",
        ("id", "name", "aliases", "deck", "description", "publisher", "characters", "api_detail_url", "site_detail_url"),
        "location",
    ),
    "GENERAL": (
        "characters",
        ("id", "name", "real_name", "aliases", "deck", "description", "publisher", "powers", "teams", "api_detail_url", "site_detail_url"),
        "character",
    ),
}
MIXED_CATEGORIES = (
    "CHARACTERS", "POWERS", "TEAMS", "COMICS", "STORY_ARCS", "MOVIES", "LOCATIONS",
)


class ComicVineError(RuntimeError):
    """A safe Comic Vine failure that never includes the API key."""


class ComicVineQuotaUnavailable(ComicVineError):
    """Comic Vine rate limit is temporarily unavailable."""


@dataclass(frozen=True)
class SourceContext:
    source_type: str
    reference: str
    title: str
    category: str
    content: str


def _plain_text(value: str, limit: int = 2500) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value))
    compact = re.sub(r"\s+", " ", without_tags).strip()
    return compact[:limit]


def _compact(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return None
    if isinstance(value, str):
        return _plain_text(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, list):
        return [item for raw in value[:20] if (item := _compact(raw, depth + 1)) not in (None, "", [], {})]
    if isinstance(value, dict):
        return {
            str(key): item
            for key, raw in value.items()
            if (item := _compact(raw, depth + 1)) not in (None, "", [], {})
        }
    return None


def _contains_marvel_publisher(value: Any) -> bool:
    if isinstance(value, dict):
        identifier = value.get("id")
        name = value.get("name")
        url = value.get("api_detail_url")
        if (
            identifier == MARVEL_PUBLISHER_ID
            or (isinstance(name, str) and name.strip().casefold() in MARVEL_NAMES)
            or (isinstance(url, str) and "/4010-31/" in url)
        ):
            return True
        return any(_contains_marvel_publisher(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_marvel_publisher(item) for item in value)
    return False


class ComicVineClient:
    def __init__(
        self,
        api_key: str,
        *,
        user_agent: str,
        page_size: int = 100,
        max_pages: int = 3,
        request_interval: float = 1.1,
        timeout: float = 60.0,
        max_retries: int = 3,
        session: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ComicVineError("COMIC_VINE_API_KEY não configurada")
        if session is None:
            try:
                import requests
            except ImportError as error:
                raise ComicVineError("requests não está instalado") from error
            session = requests.Session()
        self.api_key = api_key
        self.page_size = max(1, min(page_size, 100))
        self.max_pages = max_pages
        self.request_interval = max(0.0, request_interval)
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session
        self.sleep = sleep
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})

    def _request(self, resource: str, fields: Sequence[str], offset: int) -> Mapping[str, Any]:
        params = {
            "api_key": self.api_key,
            "format": "json",
            "limit": self.page_size,
            "offset": offset,
            "field_list": ",".join(fields),
        }
        last_error: Exception | None = None
        response = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    f"{BASE_URL}/{resource}/", params=params, timeout=self.timeout
                )
                if response.status_code == 200:
                    payload = response.json()
                    if isinstance(payload, dict) and payload.get("status_code") == 1:
                        return payload
                    api_error = (
                        str(payload.get("error", "")).casefold()
                        if isinstance(payload, dict)
                        else ""
                    )
                    if "rate limit" in api_error or "quota" in api_error:
                        raise ComicVineQuotaUnavailable(
                            "cota/rate limit da Comic Vine atingido; nenhuma pergunta foi inserida"
                        )
                    raise ComicVineError("Comic Vine retornou status de API inválido")
                if response.status_code in {420, 429}:
                    raise ComicVineQuotaUnavailable(
                        "cota/rate limit da Comic Vine atingido; nenhuma pergunta foi inserida"
                    )
                if response.status_code not in {408, 420, 429, 500, 502, 503, 504}:
                    raise ComicVineError(
                        f"Comic Vine respondeu HTTP {response.status_code}"
                    )
                last_error = RuntimeError(f"HTTP {response.status_code}")
            except ComicVineError:
                raise
            except Exception as error:
                last_error = error
            if attempt < self.max_retries:
                wait = min(max(self.request_interval, 1.5 * attempt), 5.0)
                LOGGER.warning(
                    "[RETRY] Comic Vine tentativa %s/%s em %.1fs",
                    attempt + 1, self.max_retries, wait,
                )
                self.sleep(wait)
        raise ComicVineError(
            f"falha ao consultar Comic Vine após {self.max_retries} tentativas "
            f"({type(last_error).__name__})"
        ) from last_error

    def _fetch_category(self, category: str, limit: int) -> list[SourceContext]:
        resource, fields, reference_type = RESOURCE_SPECS[category]
        contexts: list[SourceContext] = []
        seen: set[str] = set()
        offset = 0
        for page in range(self.max_pages):
            if page:
                self.sleep(self.request_interval)
            payload = self._request(resource, fields, offset)
            results = payload.get("results")
            if not isinstance(results, list) or not results:
                break
            for record in results:
                if not isinstance(record, dict) or not _contains_marvel_publisher(record):
                    continue
                identifier = record.get("id")
                title = record.get("name")
                if not isinstance(identifier, int) or identifier <= 0:
                    continue
                if not isinstance(title, str) or not title.strip():
                    continue
                reference = f"comicvine:{reference_type}:{identifier}"
                if reference in seen:
                    continue
                compact = _compact(record)
                content = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
                contexts.append(SourceContext(
                    source_type="COMIC_VINE", reference=reference,
                    title=title.strip(), category=category, content=content,
                ))
                seen.add(reference)
                if len(contexts) >= limit:
                    return contexts
            consumed = payload.get("number_of_page_results")
            offset += consumed if isinstance(consumed, int) and consumed > 0 else len(results)
            total = payload.get("number_of_total_results")
            if isinstance(total, int) and offset >= total:
                break
        return contexts

    def fetch_contexts(self, category: str, limit: int) -> list[SourceContext]:
        if category != "MIXED":
            if category not in RESOURCE_SPECS:
                raise ComicVineError(f"categoria não suportada: {category}")
            return self._fetch_category(category, limit)

        per_category = max(1, (limit + len(MIXED_CATEGORIES) - 1) // len(MIXED_CATEGORIES))
        contexts: list[SourceContext] = []
        for item in MIXED_CATEGORIES:
            try:
                contexts.extend(self._fetch_category(item, per_category))
            except ComicVineQuotaUnavailable:
                raise
            except ComicVineError as error:
                LOGGER.warning("[WARN] Contexto %s indisponível: %s", item, error)
        return contexts[:limit]


def select_contexts_for_prompt(
    contexts: Sequence[SourceContext], *, max_chars: int = 60_000
) -> list[SourceContext]:
    """Interleave categories and keep only complete blocks that fit the prompt budget."""
    queues: dict[str, list[SourceContext]] = {}
    for context in contexts:
        queues.setdefault(context.category, []).append(context)
    interleaved: list[SourceContext] = []
    while any(queues.values()):
        for queue in queues.values():
            if queue:
                interleaved.append(queue.pop(0))

    selected: list[SourceContext] = []
    length = 0
    for context in interleaved:
        block = (
            f"REFERENCE: {context.reference}\nSOURCE_TYPE: {context.source_type}\n"
            f"CATEGORY: {context.category}\nTITLE: {context.title}\nDATA: {context.content}"
        )
        if selected and length + len(block) > max_chars:
            continue
        selected.append(context)
        length += len(block)
    return selected


def serialize_contexts(contexts: Sequence[SourceContext]) -> str:
    blocks: list[str] = []
    for context in contexts:
        block = (
            f"REFERENCE: {context.reference}\nSOURCE_TYPE: {context.source_type}\n"
            f"CATEGORY: {context.category}\nTITLE: {context.title}\nDATA: {context.content}"
        )
        blocks.append(block)
    return "\n\n---\n\n".join(blocks)
