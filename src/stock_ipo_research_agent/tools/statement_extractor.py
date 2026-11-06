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

Widened after checking 9 other large companies (see scripts and tests):
- The rupee sign extracts as a stray letter ("v crore", "I crore"), so the unit is
  read from the WORD crore, million or lakh, never from the symbol.
- Column headers may read "March 31, 2026", "31st March, 2026", "March 31," over
  "2026 2025", or "2025-26". Some reports repeat the pair for a second table.
- Row labels may carry a numeral ("I", "(I)", "I."), a "Total" prefix or not, and
  note references like "2.18" or "24 F89". Rows are matched on the label words.
- Two tables can share one text line (profit and loss beside other comprehensive
  income). Only the left table is read.
- If a report has no "from continuing operations" profit row, the plain "Profit for
  the year" row is used instead and keeps its own key.

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
_UNIT_NAMES = {"crore": UNIT_INR_CRORE, "million": "INR million", "lakh": "INR lakh"}

_NUMBER = re.compile(r"^\(?\d[\d,]*(?:\.\d+)?\)?$")
_NIL = {"-", "\u2013", "\u2014"}
_NOTE = re.compile(r"^\d{1,3}(?:\([ivxl]+\)|\([a-z]\))*$")
_UNIT_WORD = re.compile(r"\b(crores?|million|lakhs?)\b", re.IGNORECASE)
_FOREIGN = re.compile(r"us\s?\$|\busd\b|\bdollars?\b", re.IGNORECASE)
_DATE = re.compile(r"(?:march\s+31|31(?:st)?\s+march),?\s+(\d{4})(\*?)", re.IGNORECASE)
_DATE_OVER_YEARS = re.compile(r"march\s+31,?\s+(\d{4})(\*?)\s+(\d{4})(\*?)", re.IGNORECASE)
_FISCAL_YEAR = re.compile(r"\b(\d{4})-(\d{2})(\*?)(?!\d)")
_NUMERAL = re.compile(r"^\(?[ivxl]+[.)]?\s+")
_HEADER_LINES = 14

# Matched against the normalised label (lower case, leading numeral removed).
HEADLINES: dict[str, re.Pattern[str]] = {
    "total_revenue_from_operations": re.compile(r"^(?:total\s+)?revenue from operations\b"),
    "other_income": re.compile(r"^other income\b"),
    "total_income": re.compile(r"^total income\b"),
    "profit_from_continuing_operations": re.compile(
        r"^profit(?:\s*/\s*\(?loss\)?)?(?:\s+after\s+tax)?\s+for\s+the\s+(?:year|period)"
        r"\s+from\s+continuing\s+operations\b"
    ),
}
# Used only when the report has no "from continuing operations" profit row.
# STRONG names the year or period; it also accepts the consolidated total
# "Profit for the year before non-controlling interests". WEAK ("Net profit after tax")
# is used only if no strong row exists, because it can come before associates' share.
PROFIT_FOR_THE_YEAR_STRONG = re.compile(
    r"^(?:net\s+)?profit(?:\s*/\s*\(?loss\)?)?(?:\s+after\s+tax)?\s+for\s+the\s+(?:year|period)"
    r"(?:\s+before\s+non-?controlling\s+interests?)?\s*(?:\(.*\))?$"
)
PROFIT_FOR_THE_YEAR = re.compile(
    r"^(?:net\s+)?profit(?:\s*/\s*\(?loss\)?)?(?:\s+after\s+tax)?"
    r"(?:\s+for\s+the\s+(?:year|period))?\s*(?:\(.*\))?$"
)


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


def _left_table_tokens(tokens: list[str]) -> list[str]:
    """Two tables can share a line. Keep only the left one.

    The first run of two or more figures is the left table's value columns (with an
    optional note in front). If words follow that run, they belong to another table.
    """
    index = 0
    while index < len(tokens):
        if parse_number(tokens[index]) is not None and tokens[index] not in _NIL:
            end = index
            while end < len(tokens) and parse_number(tokens[end]) is not None:
                end += 1
            if end - index >= 2:
                rest = tokens[end:]
                if any(re.search(r"[A-Za-z]{2,}", token) for token in rest):
                    return tokens[:end]
                return tokens
            index = end
        else:
            index += 1
    return tokens


def normalise_label(label: str) -> str:
    """Lower case, with a leading numeral such as 'I', '(I)' or 'IX.' removed."""
    return _NUMERAL.sub("", label.casefold().strip(), count=1)


def parse_row(line: str) -> ParsedRow | None:
    """Parse one statement line, or None if it does not end in two figures."""
    tokens = _left_table_tokens(line.split())
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


def _read_columns(head: str) -> list[tuple[str, bool]]:
    flat = " ".join(head.split())

    # 1. Full dates: the first two different adjacent years are the columns. A title
    #    such as "for the year ended March 31, 2026" repeats a year and is skipped.
    dates = [(m.group(1), bool(m.group(2))) for m in _DATE.finditer(flat)]
    for i in range(len(dates) - 1):
        if dates[i][0] != dates[i + 1][0]:
            pair, rest = dates[i : i + 2], [d[0] for d in dates[i + 2 :]]
            if rest in ([], [pair[0][0], pair[1][0]]):  # a second table repeats the pair
                return [(f"March 31, {year}", star) for year, star in pair]
            break

    # 2. "Year ended March 31," printed over "2026 2025".
    over = _DATE_OVER_YEARS.search(flat)
    if over and over.group(1) != over.group(3):
        return [
            (f"March 31, {over.group(1)}", bool(over.group(2))),
            (f"March 31, {over.group(3)}", bool(over.group(4))),
        ]

    # 3. Fiscal-year labels such as "2025-26 2024-25" (the year ends on March 31).
    labels = [
        (int(m.group(1)) + 1, bool(m.group(3)))
        for m in _FISCAL_YEAR.finditer(flat)
        if int(m.group(2)) == (int(m.group(1)) + 1) % 100
    ]
    if len(labels) >= 2 and labels[0][0] != labels[1][0]:
        return [(f"March 31, {year}", star) for year, star in labels[:2]]

    raise ExtractionError(f"Expected two different year columns in the header, got {dates}.")


def read_header(page_text: str) -> tuple[str, list[tuple[str, bool]]]:
    """Return (unit, [(period, starred), ...]) in the order printed."""
    head = "\n".join(page_text.splitlines()[:_HEADER_LINES])
    unit_match = _UNIT_WORD.search(head)
    if not unit_match:
        raise ExtractionError("Unit (crore, million or lakh) not found in the statement header.")
    if _FOREIGN.search(head):
        raise ExtractionError("The header mentions a foreign currency. Only INR is supported.")
    unit = _UNIT_NAMES[unit_match.group(1).casefold().rstrip("s")]
    return unit, _read_columns(head)


def extract_pl_headlines(
    location: StatementLocation, pages: list[str]
) -> list[ExtractedFigure]:
    """Headline P&L figures for one located statement, validated or an error."""
    if location.statement != PROFIT_AND_LOSS:
        raise ValueError(f"Expected a profit_and_loss location, got {location.statement}.")

    unit, columns = read_header(pages[location.pdf_pages[0] - 1])

    hits: dict[str, list[tuple[int, str, ParsedRow]]] = {key: [] for key in HEADLINES}
    plain_profit: list[tuple[int, str, ParsedRow]] = []
    strong_profit: list[tuple[int, str, ParsedRow]] = []
    for page in location.pdf_pages:
        for line in pages[page - 1].splitlines():
            row = parse_row(line)
            if row is None:
                continue
            label = normalise_label(row.label)
            for key, pattern in HEADLINES.items():
                if pattern.match(label):
                    hits[key].append((page, line.strip(), row))
            if PROFIT_FOR_THE_YEAR_STRONG.match(label):
                strong_profit.append((page, line.strip(), row))
            elif PROFIT_FOR_THE_YEAR.match(label):
                plain_profit.append((page, line.strip(), row))
    plain_profit = strong_profit or plain_profit

    if not hits["profit_from_continuing_operations"] and plain_profit:
        hits = {
            ("profit_for_the_year" if key == "profit_from_continuing_operations" else key): (
                plain_profit if key == "profit_from_continuing_operations" else found
            )
            for key, found in hits.items()
        }

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