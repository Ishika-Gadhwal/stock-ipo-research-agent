"""Choose which annual report to read. The analyst picks first; code is the fallback.

Figures are never guessed: every candidate goes through the same identity check and
extractor, and every attempt is reported in plain words.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse

from stock_ipo_research_agent.models import CompanyCandidate
from stock_ipo_research_agent.tools.annual_report_reader import DocumentReaderError
from stock_ipo_research_agent.tools.financial_facts import FinancialFacts
from stock_ipo_research_agent.tools.search import OFFICIAL, SearchClient, SearchResult, normalise_url


def _is_annual_report_pdf(result: SearchResult) -> bool:
    parsed = urlparse(result.url)
    if parsed.scheme != "https" or not parsed.path.lower().endswith(".pdf"):
        return False
    return "annual report" in result.title.casefold() or "annual_report" in parsed.path.casefold()


def _score(result: SearchResult, company: CompanyCandidate) -> int:
    score = 0
    symbol = (company.nse_symbol or "").strip().casefold()
    # NSE archive file names contain the symbol, e.g. AR_29395_TMPV_2025_2026_....pdf
    if symbol and f"_{symbol}_" in urlparse(result.url).path.casefold():
        score += 3
    if result.source_type == OFFICIAL:
        score += 2
    return score


def annual_report_candidates(
    client: SearchClient, company: CompanyCandidate, limit: int = 3
) -> list[str]:
    """Annual-report PDFs that a search really returned, best guess first."""
    found: list[SearchResult] = []
    for key in client.seen_urls:
        result = client.lookup(key)
        if result is not None and _is_annual_report_pdf(result):
            found.append(result)
    found.sort(key=lambda r: (-_score(r, company), r.url))  # url breaks ties, so it is stable
    return [r.url for r in found[:limit]]


def find_facts(
    client: SearchClient,
    company: CompanyCandidate,
    analyst_url: str | None,
    *,
    extract: Callable[[str, CompanyCandidate], FinancialFacts],
    limit: int = 3,
) -> tuple[FinancialFacts | None, list[str]]:
    """Return (facts or None, notes explaining what happened)."""
    notes: list[str] = []
    tried: set[str] = set()

    if not analyst_url:
        notes.append("The analyst did not select an annual report URL.")
    elif not client.was_seen(analyst_url):
        notes.append(f"The analyst's URL was not returned by any search: {analyst_url}")
    else:
        tried.add(normalise_url(analyst_url))
        try:
            return extract(analyst_url, company), notes
        except (DocumentReaderError, ValueError) as error:
            notes.append(f"Could not read the analyst's report: {error}")

    for url in annual_report_candidates(client, company, limit):
        if normalise_url(url) in tried:
            continue
        tried.add(normalise_url(url))
        try:
            facts = extract(url, company)
        except (DocumentReaderError, ValueError) as error:
            notes.append(f"Candidate rejected ({url}): {error}")
            continue
        notes.append(f"Fell back to an annual report PDF found by search: {url}")
        return facts, notes
    return None, notes
