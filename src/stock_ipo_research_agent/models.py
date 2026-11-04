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
