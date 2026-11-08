"""Read an annual report and return cited headline P&L figures. No LLM.

Pipeline: seen-URL check -> download + identity check -> locate P&L pages ->
extract + cross-check -> text for the agent. Anything that fails is reported as
"could not extract"; a number is never guessed.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel

from stock_ipo_research_agent.models import CompanyCandidate
from stock_ipo_research_agent.tools.annual_report_reader import (
    AnnualReportReader,
    DocumentReaderError,
)
from stock_ipo_research_agent.tools.search import SearchClient
from stock_ipo_research_agent.tools.statement_extractor import (
    ExtractedFigure,
    ExtractionError,
    extract_pl_headlines,
)
from stock_ipo_research_agent.tools.statement_locator import (
    CONSOLIDATED,
    PROFIT_AND_LOSS,
    STANDALONE,
    get_statement,
    locate_statements,
)

# The company the human confirmed. Set by code in the Flow, so the LLM cannot change it.
_confirmed_company: CompanyCandidate | None = None


def set_company(company: CompanyCandidate) -> None:
    global _confirmed_company
    _confirmed_company = company


def get_company() -> CompanyCandidate | None:
    return _confirmed_company


def reset_company() -> None:
    global _confirmed_company
    _confirmed_company = None


class FinancialFacts(BaseModel):
    source_url: str
    document_sha256: str
    total_pages: int
    identity_evidence: list[str]
    figures: list[ExtractedFigure]
    problems: list[str]  # what could not be extracted, and why


class VerifiedReportLoader(AnnualReportReader):
    """Reader that hands back all page texts, but only after the identity check passes."""

    def load(
        self, source_url: str, company: CompanyCandidate
    ) -> tuple[list[str], str, list[str]]:
        self._check_url(source_url)
        pdf_bytes = self._load_pdf(source_url)
        digest = hashlib.sha256(pdf_bytes).hexdigest()
        pages = self._load_pages(pdf_bytes, digest)
        evidence = self._validate_identity(pages, company)
        return pages, digest, evidence


def extract_pl_facts(
    source_url: str, company: CompanyCandidate, *, loader: VerifiedReportLoader | None = None
) -> FinancialFacts:
    loader = loader or VerifiedReportLoader()
    pages, digest, evidence = loader.load(source_url, company)
    locations = locate_statements(pages)

    figures: list[ExtractedFigure] = []
    problems: list[str] = []
    for basis in (CONSOLIDATED, STANDALONE):
        try:
            location = get_statement(locations, PROFIT_AND_LOSS, basis)
        except ValueError as error:
            problems.append(f"{basis}: {error}")
            continue
        if location is None:
            problems.append(f"{basis}: profit and loss statement not found in this document")
            continue
        try:
            figures.extend(extract_pl_headlines(location, pages))
        except ExtractionError as error:
            problems.append(f"{basis}: could not extract safely ({error})")

    return FinancialFacts(
        source_url=source_url,
        document_sha256=digest,
        total_pages=len(pages),
        identity_evidence=evidence,
        figures=figures,
        problems=problems,
    )


def _name(key: str) -> str:
    return key.replace("_", " ").capitalize()


def format_facts(facts: FinancialFacts) -> str:
    """Text the agent reads. Every figure comes with its page and source line."""
    lines = [
        f"Document: {facts.source_url}",
        f"Pages: {facts.total_pages} | SHA-256: {facts.document_sha256[:12]}",
        "Identity check: " + "; ".join(facts.identity_evidence),
        "",
        "Figures extracted by code (report them exactly as shown, with the page):",
    ]
    if not facts.figures:
        lines.append("- none")
    for f in facts.figures:
        star = " (column marked *)" if f.starred else ""
        lines.append(
            f"- {f.basis.capitalize()} | {_name(f.key)} | year ended {f.period}{star} "
            f"| {f.value:,} {f.unit} | PDF page {f.page_label} | line: {f.source_line}"
        )
    if facts.problems:
        lines += ["", "Could not extract (say 'not found', never estimate):"]
        lines += [f"- {p}" for p in facts.problems]
    return "\n".join(lines)


def read_facts_for_agent(
    report_url: str,
    client: SearchClient,
    company: CompanyCandidate | None,
    *,
    loader: VerifiedReportLoader | None = None,
) -> str:
    """What the agent's tool calls. Refuses instead of guessing."""
    if not client.was_seen(report_url):
        return (
            "Refused: this URL was not returned by any search. "
            "Use a URL from the search results, copied exactly. Do not report any figures."
        )
    if company is None:
        return "Refused: no company has been confirmed yet. Do not report any figures."
    try:
        facts = extract_pl_facts(report_url, company, loader=loader)
    except (DocumentReaderError, ValueError) as error:
        return (
            f"Could not read the report: {error}. "
            "Do not guess any figures; say they were not found."
        )
    return format_facts(facts)