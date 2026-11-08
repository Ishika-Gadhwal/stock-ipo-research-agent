"""Search that returns source URLs and dates, and remembers every URL it returned.

Plain Python (requests only) so it can be unit-tested without CrewAI or API calls.
The CrewAI wrapper lives in source_search_tool.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import requests

SERPER_URL = "https://google.serper.dev/search"
OFFICIAL_DOMAINS = ("nseindia.com", "bseindia.com", "sebi.gov.in")
OFFICIAL = "official"
UNVERIFIED = "unverified"


class SearchError(RuntimeError):
    """The search could not be completed."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    date: str | None  # as shown by the search engine, None when not given
    source_type: str  # "official" or "unverified", assigned by code, not by the LLM


def normalise_url(url: str) -> str:
    """Lower-case scheme and host, drop fragment and trailing slash."""
    parsed = urlparse(url.strip())
    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", parsed.query, "")
    )


def classify_source(url: str) -> str:
    """'official' only for the exchanges and SEBI (host or a true sub-domain)."""
    host = (urlparse(url).hostname or "").lower()
    for domain in OFFICIAL_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return OFFICIAL
    return UNVERIFIED


def format_results(results: list[SearchResult]) -> str:
    """Text the agent reads. Every URL it may cite is listed here, nowhere else."""
    if not results:
        return "No results found."
    blocks = []
    for number, r in enumerate(results, start=1):
        blocks.append(
            f"[{number}] {r.title}\n"
            f"    URL: {r.url}\n"
            f"    Date: {r.date or 'not stated'}\n"
            f"    Source type: {r.source_type}\n"
            f"    Snippet: {r.snippet}"
        )
    return "\n".join(blocks)


class SearchClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        max_results: int = 5,
        timeout: int = 20,
        session: requests.Session | None = None,
    ) -> None:
        self._api_key = api_key
        self.max_results = max_results
        self.timeout = timeout
        self._session = session or requests.Session()
        self._seen: dict[str, SearchResult] = {}
        self._snippets: list[str] = []  # every snippet of every search, never overwritten

    def search(self, query: str) -> list[SearchResult]:
        query = query.strip()
        if not query:
            raise ValueError("Search query must not be empty.")
        key = self._api_key or os.environ.get("SERPER_API_KEY")
        if not key:
            raise SearchError("SERPER_API_KEY is not set.")
        try:
            response = self._session.post(
                SERPER_URL,
                headers={"X-API-KEY": key, "Content-Type": "application/json"},
                json={"q": query, "num": self.max_results, "gl": "in"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            raise SearchError(f"Search failed: {error}") from error

        results: list[SearchResult] = []
        for item in data.get("organic", []):
            url = (item.get("link") or "").strip()
            title = (item.get("title") or "").strip()
            if not url or not title:
                continue
            result = SearchResult(
                title=title,
                url=url,
                snippet=(item.get("snippet") or "").strip(),
                date=(item.get("date") or "").strip() or None,
                source_type=classify_source(url),
            )
            results.append(result)
            self._seen[normalise_url(url)] = result
            self._snippets.append(f"{title} {result.snippet}")
        return results

    def was_seen(self, url: str) -> bool:
        """True only if this exact URL (ignoring case of host, fragment, trailing /) was returned."""
        return normalise_url(url) in self._seen

    def lookup(self, url: str) -> SearchResult | None:
        """The real search result for this URL, or None if no search ever returned it."""
        return self._seen.get(normalise_url(url))

    def all_snippets(self) -> list[str]:
        """Every title and snippet returned in this run. A URL returned twice with two
        different snippets keeps both (the registry in _seen keeps only the last)."""
        return list(self._snippets)

    def all_results(self) -> list[SearchResult]:
        """Every result returned in this run (used to trace numbers in unverified text)."""
        return list(self._seen.values())

    @property
    def seen_urls(self) -> frozenset[str]:
        return frozenset(self._seen)


_shared_client: SearchClient | None = None


def get_search_client() -> SearchClient:
    """One client shared by all crews in a run, so seen URLs accumulate."""
    global _shared_client
    if _shared_client is None:
        _shared_client = SearchClient()
    return _shared_client


def reset_search_client() -> None:
    """Start a fresh, empty registry (call at the start of every run)."""
    global _shared_client
    _shared_client = None