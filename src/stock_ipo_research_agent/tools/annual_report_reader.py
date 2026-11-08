"""Deterministic, citable extraction from annual-report PDFs."""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pdfplumber
import requests

from stock_ipo_research_agent.models import (
    AnnualReportReadResult,
    CompanyCandidate,
    DocumentExcerpt,
)

HEADING_CHARS = 400
_FORMERLY = re.compile(r"\(\s*formerly\b[^)]*\)", re.IGNORECASE)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).casefold()



SPREAD_BREAK = "\f"  # separates the left and right half of a two-page spread
_SPREAD_RATIO = 1.2  # a page wider than 1.2 x its height is treated as a spread

class DocumentReaderError(RuntimeError):
    """The document could not safely be downloaded or read."""


class DocumentIdentityError(DocumentReaderError):
    """The PDF does not contain enough evidence for the selected company."""


class AnnualReportReader:
    """Fetch, validate and search an annual-report PDF without using an LLM."""

    def __init__(
        self,
        cache_dir: Path | str = "cache",
        *,
        timeout_seconds: int = 120,
        max_download_bytes: int = 50 * 1024 * 1024,
        identity_page_limit: int = 15,
        require_identifier: bool = True,
        allowed_hosts: set[str] | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.timeout_seconds = timeout_seconds
        self.max_download_bytes = max_download_bytes
        self.identity_page_limit = identity_page_limit
        self.require_identifier = require_identifier
        self.allowed_hosts = allowed_hosts

    def read(
        self,
        source_url: str,
        company: CompanyCandidate,
        terms: list[str],
        *,
        context_pages: int = 1,
        max_excerpt_pages: int = 8,
        page_range: tuple[int, int] | None = None,
        heading_only: bool = False,
    ) -> AnnualReportReadResult:
        """Return bounded, citable excerpts after verifying document identity.

        page_range is 1-based PDF pages, inclusive. heading_only keeps only pages
        where a term appears at the top of the page (statement headings).
        """
        clean_terms = self._clean_terms(terms)
        if not clean_terms:
            raise ValueError("Provide at least one non-empty search term.")
        if context_pages < 0 or max_excerpt_pages < 1:
            raise ValueError("context_pages must be >= 0 and max_excerpt_pages must be >= 1.")
        if page_range and not 1 <= page_range[0] <= page_range[1]:
            raise ValueError("page_range must be (start, end) with 1 <= start <= end.")
        self._check_url(source_url)

        pdf_bytes = self._load_pdf(source_url)
        digest = hashlib.sha256(pdf_bytes).hexdigest()
        pages = self._load_pages(pdf_bytes, digest)
        evidence = self._validate_identity(pages, company)
        strength = "identifier" if any(e.startswith("Identifier:") for e in evidence) else "name_only"
        excerpts = self._find_excerpts(
            pages,
            clean_terms,
            context_pages=context_pages,
            max_excerpt_pages=max_excerpt_pages,
            page_range=page_range,
            heading_only=heading_only,
        )
        return AnnualReportReadResult(
            source_url=source_url,
            document_sha256=digest,
            total_pages=len(pages),
            identity_strength=strength,
            identity_evidence=evidence,
            excerpts=excerpts,
        )

    def _check_url(self, source_url: str) -> None:
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise DocumentReaderError("Only https URLs are allowed.")
        if self.allowed_hosts is not None and parsed.hostname not in self.allowed_hosts:
            raise DocumentReaderError(f"Host not in the allowed list: {parsed.hostname}")

    def _load_pdf(self, source_url: str) -> bytes:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.sha256(source_url.encode()).hexdigest()
        cache_path = self.cache_dir / f"annual_report_{url_hash}.pdf"
        if cache_path.exists():
            content = cache_path.read_bytes()
            if content.startswith(b"%PDF-"):
                return content
            cache_path.unlink()

        try:
            response = requests.get(
                source_url,
                headers={"User-Agent": "Mozilla/5.0 (annual-report-reader)"},
                timeout=self.timeout_seconds,
                stream=True,
            )
        except requests.RequestException as error:
            raise DocumentReaderError(f"Could not download annual report: {error}") from error

        try:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            chunks: list[bytes] = []
            received = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                received += len(chunk)
                if received > self.max_download_bytes:
                    raise DocumentReaderError("Annual report exceeds the configured download limit.")
                chunks.append(chunk)
        except requests.RequestException as error:
            raise DocumentReaderError(f"Could not download annual report: {error}") from error
        finally:
            response.close()

        content = b"".join(chunks)
        if "pdf" not in content_type and not content.startswith(b"%PDF-"):
            raise DocumentReaderError("Downloaded content is not a PDF.")
        if not content.startswith(b"%PDF-"):
            raise DocumentReaderError("Downloaded file does not have a valid PDF signature.")
        tmp_path = cache_path.with_suffix(".tmp")
        tmp_path.write_bytes(content)
        tmp_path.replace(cache_path)  # atomic: no half-written cache file
        return content

    def _load_pages(self, pdf_bytes: bytes, digest: str) -> list[str]:
        """Extract once (about 90 s for 585 pages), then reuse from the cache."""
        path = self.cache_dir / f"annual_report_{digest}.pages.v2.json"  # v2: spreads are split in halves
        if path.exists():
            try:
                pages = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(pages, list) and all(isinstance(p, str) for p in pages):
                    return pages
            except (OSError, json.JSONDecodeError):
                pass
        pages = self._extract_pages(pdf_bytes)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(pages), encoding="utf-8")
        tmp.replace(path)
        return pages

    @staticmethod
    def _page_text(page) -> str:
        """Text of one PDF page.

        A wide page is a two-page spread (two printed pages side by side). Reading it as
        one block mixes the two pages, so each half is read on its own and the halves are
        joined with SPREAD_BREAK. A normal page has no break, so its text is unchanged.
        """
        if page.width > page.height * _SPREAD_RATIO:
            x0, top, x1, bottom = page.bbox
            middle = (x0 + x1) / 2
            halves = (
                page.crop((x0, top, middle, bottom)).extract_text() or "",
                page.crop((middle, top, x1, bottom)).extract_text() or "",
            )
            return SPREAD_BREAK.join(halves)
        return page.extract_text() or ""

    @staticmethod
    def _extract_pages(pdf_bytes: bytes) -> list[str]:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages = [AnnualReportReader._page_text(page) for page in pdf.pages]
        except Exception as error:
            raise DocumentReaderError(f"Could not extract text from annual report: {error}") from error
        if not pages:
            raise DocumentReaderError("Annual report contains no pages.")
        return pages

    def _validate_identity(self, pages: list[str], company: CompanyCandidate) -> list[str]:
        legal_name = company.legal_name.strip()
        # Drop "(formerly X)" so an old name is not mistaken for the current entity.
        front = _FORMERLY.sub(" ", _normalise("\n".join(pages[: self.identity_page_limit])))
        name_pattern = rf"(?<![a-z0-9]){re.escape(_normalise(legal_name))}(?![a-z0-9])"
        if not legal_name or not re.search(name_pattern, front):
            raise DocumentIdentityError(
                f"Document does not name the selected company as its current legal name "
                f"in its first {self.identity_page_limit} pages."
            )

        full_text = _normalise("\n".join(pages))
        matched = self._matched_identifiers(full_text, company)
        has_identifiers = any((company.isin, company.nse_symbol, company.bse_code))
        if self.require_identifier and has_identifiers and not matched:
            raise DocumentIdentityError(
                "Document names the company but none of its ISIN, labelled NSE symbol "
                "or labelled BSE code appears anywhere in it."
            )

        evidence = [f"Legal name: {legal_name}"]
        evidence.extend(f"Identifier: {value}" for value in matched)
        if has_identifiers and not matched:
            evidence.append("No exact exchange identifier found in document")
        return evidence

    @staticmethod
    def _matched_identifiers(text: str, company: CompanyCandidate) -> list[str]:
        matched: list[str] = []
        if company.isin:
            isin = re.escape(company.isin.strip().casefold())
            if re.search(rf"(?<![a-z0-9]){isin}(?![a-z0-9])", text):
                matched.append(company.isin.strip())
        for value in (company.nse_symbol, company.bse_code):
            if not value or not value.strip():
                continue
            ident = re.escape(value.strip().casefold())
            # Short symbols need an exchange label, e.g. "NSE - Stock Code TMPV".
            labelled = (
                rf"(?:nse|bse)\b[^a-z0-9]{{0,5}}(?:(?:stock|scrip|trading)\s+)?"
                rf"(?:symbol|code|no\.?)?[^a-z0-9]{{0,5}}{ident}(?![a-z0-9])"
            )
            if re.search(labelled, text):
                matched.append(value.strip())
        return matched

    @staticmethod
    def _clean_terms(terms: list[str]) -> list[str]:
        return list(dict.fromkeys(term.strip() for term in terms if term.strip()))

    @staticmethod
    def _find_excerpts(
        pages: list[str],
        terms: list[str],
        *,
        context_pages: int,
        max_excerpt_pages: int,
        page_range: tuple[int, int] | None = None,
        heading_only: bool = False,
    ) -> list[DocumentExcerpt]:
        norm_terms = [(term, _normalise(term)) for term in terms]
        first, last = page_range or (1, len(pages))

        scored: list[tuple[int, int]] = []
        for index, text in enumerate(pages):
            if not first <= index + 1 <= last:
                continue
            norm = _normalise(text)
            heading = norm[:HEADING_CHARS]
            in_heading = sum(1 for _, n in norm_terms if n in heading)
            anywhere = sum(1 for _, n in norm_terms if n in norm)
            if not anywhere or (heading_only and not in_heading):
                continue
            scored.append((-(in_heading * 10 + anywhere), index))  # best pages first
        scored.sort()

        selected: list[int] = []
        for _, hit in scored:
            for index in range(max(0, hit - context_pages), min(len(pages), hit + context_pages + 1)):
                if index not in selected:
                    selected.append(index)
                if len(selected) >= max_excerpt_pages:
                    break
            if len(selected) >= max_excerpt_pages:
                break

        return [
            DocumentExcerpt(
                pdf_page=index + 1,
                text=pages[index],
                matched_terms=[t for t, n in norm_terms if n in _normalise(pages[index])],
            )
            for index in sorted(selected)
        ]