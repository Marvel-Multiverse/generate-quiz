from __future__ import annotations

import unittest

from src.comic_vine_client import (
    ComicVineClient,
    ComicVineQuotaUnavailable,
    SourceContext,
    select_contexts_for_prompt,
)
from src.web.research_client import TavilyResearchClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http failure")


class FakeSession:
    def __init__(self, get_payload=None, post_payload=None):
        self.headers = {}
        self.get_payload = get_payload
        self.post_payload = post_payload
        self.get_calls = []
        self.post_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return FakeResponse(self.get_payload)

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return FakeResponse(self.post_payload)


class SourceClientTests(unittest.TestCase):
    def test_comic_vine_filters_non_marvel_and_builds_reference(self):
        payload = {
            "status_code": 1,
            "number_of_page_results": 2,
            "number_of_total_results": 2,
            "results": [
                {"id": 1443, "name": "Spider-Man", "real_name": "Peter Parker", "publisher": {"id": 31, "name": "Marvel"}},
                {"id": 1699, "name": "Batman", "publisher": {"id": 10, "name": "DC Comics"}},
            ],
        }
        session = FakeSession(get_payload=payload)
        client = ComicVineClient(
            "secret", user_agent="tests", session=session, sleep=lambda _: None,
            max_pages=1,
        )
        contexts = client.fetch_contexts("CHARACTERS", 10)
        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0].reference, "comicvine:character:1443")
        self.assertIn("Peter Parker", contexts[0].content)
        self.assertEqual(len(session.get_calls), 1)

    def test_web_client_keeps_only_trusted_domains(self):
        payload = {"results": [
            {"url": "https://www.marvel.com/characters/spider-man", "title": "Spider-Man", "content": "Peter Parker is Spider-Man."},
            {"url": "https://random-blog.example/post", "title": "Rumor", "content": "Unsupported."},
        ]}
        session = FakeSession(post_payload=payload)
        client = TavilyResearchClient(
            "secret", ["marvel.com"], session=session, max_results=5
        )
        results = client.enrich([
            SourceContext("COMIC_VINE", "comicvine:character:1443", "Spider-Man", "CHARACTERS", "data")
        ])
        self.assertEqual([item.reference for item in results], ["https://www.marvel.com/characters/spider-man"])

    def test_prompt_budget_interleaves_categories(self):
        contexts = [
            SourceContext("COMIC_VINE", f"character:{index}", f"C{index}", "CHARACTERS", "x" * 100)
            for index in range(3)
        ] + [
            SourceContext("COMIC_VINE", f"team:{index}", f"T{index}", "TEAMS", "x" * 100)
            for index in range(3)
        ]
        selected = select_contexts_for_prompt(contexts, max_chars=400)
        self.assertEqual([item.category for item in selected[:2]], ["CHARACTERS", "TEAMS"])

    def test_comic_vine_quota_is_reported_without_retries(self):
        session = FakeSession(get_payload={})
        session.get = lambda *args, **kwargs: FakeResponse({}, status_code=429)
        client = ComicVineClient(
            "secret", user_agent="tests", session=session, sleep=lambda _: None,
            max_retries=3,
        )
        with self.assertRaises(ComicVineQuotaUnavailable):
            client.fetch_contexts("CHARACTERS", 1)

    def test_comic_vine_quota_inside_json_is_reported(self):
        session = FakeSession(get_payload={"status_code": 0, "error": "Rate limit exceeded"})
        client = ComicVineClient(
            "secret", user_agent="tests", session=session, sleep=lambda _: None,
            max_retries=1,
        )
        with self.assertRaises(ComicVineQuotaUnavailable):
            client.fetch_contexts("CHARACTERS", 1)


if __name__ == "__main__":
    unittest.main()
