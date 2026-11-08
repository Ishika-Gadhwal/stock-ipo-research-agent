from typing import Literal

from pydantic import BaseModel


class CompanyCandidate(BaseModel):
    legal_name: str
    nse_symbol: str | None = None
    bse_code: str | None = None
    isin: str | None = None
    business: str
    source_url: str


class IdentityResult(BaseModel):
    candidates: list[CompanyCandidate]


class DocumentExcerpt(BaseModel):
    """A bounded, citable section of a source document."""

    pdf_page: int
    text: str
    matched_terms: list[str]


class AnnualReportReadResult(BaseModel):
    source_url: str
    document_sha256: str
    total_pages: int
    identity_strength: str  # "identifier" or "name_only"
    identity_evidence: list[str]
    excerpts: list[DocumentExcerpt]

class SelectedSources(BaseModel):
    """What the research agent returns: only a pick of URLs from its search results.

    Titles, dates and the official/unverified label are added by code, not by the agent.
    """

    urls: list[str]
    not_found: list[str] = []

class AnalystNote(BaseModel):
    """The financial analyst's output. The figures table itself is built by code."""

    report_url: str | None = None  # the annual report URL given to the tool, or None
    notes: str


class Narrative(BaseModel):
    """The report writer's output: a short summary. Its numbers are checked by code."""

    summary: str

class ReportChoice(BaseModel):
    """The report picker's output: only which annual report URL to read."""

    report_url: str | None = None  # a URL from the selected sources, or None

class WebSummary(BaseModel):
    """The web researcher's output. UNVERIFIED: written from search snippets, not the PDF."""

    summary: str
    source_urls: list[str] = []


class IpoView(BaseModel):
    """IPO news output. UNVERIFIED: written from search snippets, not from the offer document."""

    summary: str
    pros: list[str] = []
    cons: list[str] = []
    lean: Literal["apply", "neutral", "avoid"] = "neutral"
    lean_reason: str = ""
    confidence: Literal["low", "medium", "high"] = "low"
    source_urls: list[str] = []
