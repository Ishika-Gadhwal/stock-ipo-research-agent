"""Deterministic extraction of headline figures from a located P&L statement.

No LLM. Every figure carries its PDF page, statement, basis, unit, period and the
raw source line, and nothing is returned unless the arithmetic cross-check passes.

Layout facts learned from the TMPV FY26 report (page 332 and 456 probes):
- One data row per line: label, optional note, current year, previous year.
- Rule: the LAST TWO numeric tokens are the two year columns. A token before
  them that looks like a note (34, 37(ii)(b)) is the note. This matters because
  a real value can be tiny and look like a note (e.g. "... for sale 6 3,645").
- Brackets mean negative: (1,377). A lone dash means nil.
- Some labels wrap onto a second line, so the figures sit on the NEXT line.
  Wrapped rows are not supported: a needed row that wraps raises ExtractionError.
- Wording differs by basis, so rows are matched by label wording, not by numeral.

Assumption (checked by the cross-check, not guaranteed): every data row prints
both years, with nil shown as "-".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel

from stock_ipo_research_agent.tools.statement_locator import (
    PROFIT_AND_LOSS,
    StatementLocation,
)

UNIT_INR_CRORE = "INR crore"

_NUMBER = re.compile(r"^\(?\d[\d,]*(?:\.\d+)?\)?$")
_NIL = {"-", "\u2013", "\u2014"}
_NOTE = re.compile(r"^\d{1,3}(?:\([ivxl]+\)|\([a-z]\))*$")
_UNIT = re.compile(r"\(\s*\u20b9\s*in\s*crores?\s*\)", re.IGNORECASE)
_COLUMN = re.compile(r"march\s+31,\s+(\d{4})(\*?)", re.IGNORECASE)
_HEADER_LINES = 12

# Matched against the lower-cased row label (note and figures already removed).
HEADLINES: dict[str, re.Pattern[str]] = {
    "total_revenue_from_operations": re.compile(r"^i\.\s+total revenue from operations\b"),
    "other_income": re.compile(r"^ii\.\s+other income\b"),
    "total_income": re.compile(r"^iii\.\s+total income\b"),
    "profit_from_continuing_operations": re.compile(
        r"^[ivxl]+\.\s+profit(?:/\(loss\))?(?: after tax)? "
        r"for the year from continuing operations\b"
    ),
}


class ExtractionError(RuntimeError):
    """A figure could not be extracted safely. Better missing than wrong."""


@dataclass(frozen=True)
class ParsedRow:
    label: str
    note: str | None
    current: Decimal
    previous: Decimal


class ExtractedFigure(BaseModel):
    """One number, with everything needed to cite and interpret it."""

    key: str
    label: str
    value: Decimal
    unit: str
    period: str  # e.g. "March 31, 2026"
    # True when the column header carries a "*". It is a footnote marker (here the
    # comparative year); read the footnote before calling it "restated".
    starred: bool
    statement: str
    basis: str
    pdf_page: int
    source_line: str


def parse_number(token: str) -> Decimal | None:
    """'335,582' -> 335582, '(1,377)' -> -1377, '-' -> 0, anything else -> None."""
    if token in _NIL:
        return Decimal(0)
    if not _NUMBER.match(token):
        return None
    negative = token.startswith("(")
    if negative != token.endswith(")"):
        return None
    value = Decimal(token.strip("()").replace(",", ""))
    return -value if negative else value


def parse_row(line: str) -> ParsedRow | None:
    """Parse one statement line, or None if it does not end in two figures."""
    tokens = line.split()
    values: list[Decimal] = []
    end = len(tokens)
    while end > 0 and len(values) < 2:
        number = parse_number(tokens[end - 1])
        if number is None:
            break
        values.append(number)
        end -= 1
    if len(values) < 2:
        return None  # section header, note-only line, or a wrapped label
    label_tokens = tokens[:end]
    note = None
    if label_tokens and _NOTE.match(label_tokens[-1]):
        note = label_tokens.pop()
    return ParsedRow(" ".join(label_tokens), note, current=values[1], previous=values[0])


def read_header(page_text: str) -> tuple[str, list[tuple[str, bool]]]:
    """Return (unit, [(period, starred), ...]) in the order printed."""
    head = "\n".join(page_text.splitlines()[:_HEADER_LINES])
    if not _UNIT.search(head):
        raise ExtractionError("Unit '(INR in crores)' not found in the statement header.")
    columns = [(f"March 31, {year}", bool(star)) for year, star in _COLUMN.findall(head)]
    if len(columns) != 2 or columns[0][0] == columns[1][0]:
        raise ExtractionError(f"Expected two different year columns in the header, got {columns}.")
    return UNIT_INR_CRORE, columns


def extract_pl_headlines(
    location: StatementLocation, pages: list[str]
) -> list[ExtractedFigure]:
    """Headline P&L figures for one located statement, validated or an error."""
    if location.statement != PROFIT_AND_LOSS:
        raise ValueError(f"Expected a profit_and_loss location, got {location.statement}.")

    unit, columns = read_header(pages[location.pdf_pages[0] - 1])

    hits: dict[str, list[tuple[int, str, ParsedRow]]] = {key: [] for key in HEADLINES}
    for page in location.pdf_pages:
        for line in pages[page - 1].splitlines():
            row = parse_row(line)
            if row is None:
                continue
            label = row.label.casefold()
            for key, pattern in HEADLINES.items():
                if pattern.match(label):
                    hits[key].append((page, line.strip(), row))

    figures: list[ExtractedFigure] = []
    for key, found in hits.items():
        if len(found) != 1:
            raise ExtractionError(
                f"Expected exactly one '{key}' row on pages {list(location.pdf_pages)}, "
                f"found {len(found)}. The row may be missing or wrapped."
            )
        page, line, row = found[0]
        for (period, starred), value in zip(columns, (row.current, row.previous)):
            figures.append(
                ExtractedFigure(
                    key=key,
                    label=row.label,
                    value=value,
                    unit=unit,
                    period=period,
                    starred=starred,
                    statement=location.statement,
                    basis=location.basis,
                    pdf_page=page,
                    source_line=line,
                )
            )
    _check_income_identity(figures, columns)
    return figures


def _check_income_identity(
    figures: list[ExtractedFigure], columns: list[tuple[str, bool]]
) -> None:
    """Total income must equal revenue + other income in BOTH years.

    Catches column misalignment and note numbers mistaken for values.
    """
    by = {(f.key, f.period): f.value for f in figures}
    for period, _ in columns:
        revenue = by[("total_revenue_from_operations", period)]
        other = by[("other_income", period)]
        total = by[("total_income", period)]
        if revenue + other != total:
            raise ExtractionError(
                f"Cross-check failed for {period}: {revenue} + {other} != {total}."
            )