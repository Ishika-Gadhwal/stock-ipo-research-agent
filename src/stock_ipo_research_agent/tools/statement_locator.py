"""Deterministic locator for primary financial statements in annual-report text.

No LLM. Works on the list of page strings that AnnualReportReader extracts.

Rules (learned from the TMPV FY26 integrated report):
1. A statement page's text STARTS with the statement title, and "in crore"
   appears near the start. Notes pages start with "notes forming part of ...",
   and sub-tables start with "b. statement of ..." or "re-presented ...",
   so anchoring at the very start rejects them.
2. A leading "consolidated" gives the basis. No prefix means standalone
   (this report's convention; verify on other companies).
3. A page that repeats the same heading right after the previous page is the
   same statement (332/333, 334/335).
4. A page right after a statement page that starts with "(INR in crores)" and
   has no title is a continuation (standalone cash flow, 458). Capped so a
   notes page cannot be swallowed.

Known limitation: "statement of changes in equity" pages are rotated in this PDF
and extract as reversed text, so they are deliberately not located.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BALANCE_SHEET = "balance_sheet"
PROFIT_AND_LOSS = "profit_and_loss"
CASH_FLOW = "cash_flow"

CONSOLIDATED = "consolidated"
STANDALONE = "standalone"

_TITLES = {
    "balance sheet": BALANCE_SHEET,
    "statement of profit and loss": PROFIT_AND_LOSS,
    "statement of cash flows": CASH_FLOW,
}
_TITLE = re.compile(
    r"^(consolidated\s+)?(balance sheet|statement of profit and loss|statement of cash flows)\b"
)
_CONTINUATION = re.compile(r"^\(\s*\u20b9\s*in\s*crores?\s*\)")
_UNIT_WINDOW = 200


@dataclass(frozen=True)
class StatementLocation:
    """Where one statement lives. pdf_pages are 1-based PDF page numbers."""

    statement: str
    basis: str
    pdf_pages: tuple[int, ...]


def _flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def locate_statements(pages: list[str], max_continuation: int = 2) -> list[StatementLocation]:
    """Find primary statements. Returns them in document order."""
    found: list[tuple[str, str, list[int]]] = []  # statement, basis, pages
    extra = 0
    for number, text in enumerate(pages, start=1):
        flat = _flatten(text)
        match = _TITLE.match(flat)
        previous = found[-1] if found else None
        contiguous = previous is not None and previous[2][-1] == number - 1

        if match and "in crore" in flat[:_UNIT_WINDOW]:
            statement = _TITLES[match.group(2)]
            basis = CONSOLIDATED if match.group(1) else STANDALONE
            if contiguous and (previous[0], previous[1]) == (statement, basis):
                previous[2].append(number)
            else:
                found.append((statement, basis, [number]))
            extra = 0
        elif contiguous and extra < max_continuation and _CONTINUATION.match(flat):
            previous[2].append(number)
            extra += 1
    return [StatementLocation(s, b, tuple(p)) for s, b, p in found]


def get_statement(
    locations: list[StatementLocation], statement: str, basis: str
) -> StatementLocation | None:
    """Return the single matching location, None if absent, error if ambiguous."""
    matches = [loc for loc in locations if loc.statement == statement and loc.basis == basis]
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous: {len(matches)} locations for {basis} {statement}: "
            f"{[m.pdf_pages for m in matches]}"
        )
    return matches[0] if matches else None