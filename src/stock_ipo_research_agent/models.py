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