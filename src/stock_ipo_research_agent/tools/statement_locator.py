"""Deterministic locator for primary financial statements in annual-report text.

No LLM. Works on the list of page strings that AnnualReportReader extracts.

Rules (learned from TMPV, then widened after checking 9 other large companies):
1. The statement title must appear near the START of the page. A short page header
   (report name, page number, "Financial Statements") may come first, so the title
   may start up to 150 characters in. A title that follows words such as "notes",
   "auditor", "b." or "the" is a mention or a sub-table and is rejected. A unit word (crore, million or lakh) must follow within 450 characters.
2. A leading "consolidated" gives the basis. "standalone", or no prefix, means
   standalone.
3. For a page that STARTS a profit and loss, it must also contain "total income" and
   "revenue from operations", which rejects contents pages and notes pages. A page that
   repeats the previous statement's heading is exempt (it is the continuation).
4. A page that repeats the same heading right after the previous page is the same
   statement (332/333, 334/335).
5. A page right after a statement page that starts with a unit line and has no title
   is a continuation. Capped so a notes page cannot be swallowed.

Two-page spreads: the reader joins the two halves of a wide page with SPREAD_BREAK, and
each half is located as its own part. Known limit: statement of changes in equity pages are deliberately not located.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from stock_ipo_research_agent.tools.annual_report_reader import SPREAD_BREAK

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
    r"(consolidated\s+|standalone\s+)?"
    r"(balance sheet|statement of profit and loss|statement of cash flows)\b"
)
_TITLE_START_LIMIT = 150  # chars of page header allowed before the title
# Words before a title that mean it is a mention or a sub-table, not the statement itself.
_NOT_A_TITLE_PREFIX = re.compile(
    r"\b(notes?|re-?presented|restated|auditor\S*|independent|forming|following|contd)\b"
    r"|\b[a-z][.)]\s*$"  # "b. Statement of ..." / "d) Statement of ..."
    r"|\b(the|of|in|to|see|refer|and|for|our|an?)\s*$"  # prose such as "see the Balance Sheet"
)
_UNIT_WORD = re.compile(r"\b(?:crores?|million|lakhs?)\b")
_UNIT_WINDOW = 450  # chars after the title in which the unit word must appear
# The rupee sign often extracts as a stray letter, so only the unit word is relied on.
_CONTINUATION = re.compile(
    r"^\(\s*(?:\S{0,3}\s*)?(?:in\s*)?(?:\S{0,3}\s*)?(?:crores?|million|lakhs?)\b"
)


@dataclass(frozen=True)
class StatementLocation:
    """Where one statement lives. pdf_pages are 1-based PDF page numbers."""

    statement: str
    basis: str
    pdf_pages: tuple[int, ...]
    # (pdf_page, half) for each piece read. half is 0 for a normal page; 0 (left) or 1
    # (right) on a two-page spread. Not part of equality, so pdf_pages alone identifies it.
    parts: tuple[tuple[int, int], ...] = field(default=(), compare=False)


def part_text(pages: list[str], pdf_page: int, half: int = 0) -> str:
    """Text of one part: a whole normal page, or one half of a spread."""
    pieces = pages[pdf_page - 1].split(SPREAD_BREAK)
    return pieces[half] if half < len(pieces) else ""


def _flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def locate_statements(pages: list[str], max_continuation: int = 2) -> list[StatementLocation]:
    """Find primary statements. Returns them in document order."""
    # Each half of a spread is its own part. For a normal page, part number = page number.
    parts = [
        (page, half, piece)
        for page, text in enumerate(pages, start=1)
        for half, piece in enumerate(text.split(SPREAD_BREAK))
    ]
    found: list[tuple[str, str, list[int]]] = []  # statement, basis, part numbers
    extra = 0
    for number, (_, _, text) in enumerate(parts, start=1):
        flat = _flatten(text)
        match = _TITLE.search(flat)
        if match and (
            match.start() > _TITLE_START_LIMIT
            or _NOT_A_TITLE_PREFIX.search(flat[: match.start()])
        ):
            match = None
        previous = found[-1] if found else None
        contiguous = previous is not None and previous[2][-1] == number - 1

        statement = _TITLES[match.group(2)] if match else None
        basis = None
        accepted = False
        if match and _UNIT_WORD.search(flat[match.start() : match.start() + _UNIT_WINDOW]):
            basis = CONSOLIDATED if (match.group(1) or "").strip() == "consolidated" else STANDALONE
            repeat = contiguous and (previous[0], previous[1]) == (statement, basis)
            # The income-rows check is for a page that STARTS a profit and loss. A page that
            # repeats the previous statement's heading is its continuation (332/333) and may
            # hold only the lower rows.
            accepted = (
                statement != PROFIT_AND_LOSS
                or repeat
                or ("total income" in flat and "revenue from operations" in flat)
            )

        if accepted:
            if contiguous and (previous[0], previous[1]) == (statement, basis):
                previous[2].append(number)
            else:
                found.append((statement, basis, [number]))
            extra = 0
        elif contiguous and extra < max_continuation and _CONTINUATION.match(flat):
            previous[2].append(number)
            extra += 1
    locations = []
    for statement, basis, numbers in found:
        pieces = tuple((parts[n - 1][0], parts[n - 1][1]) for n in numbers)
        pdf_pages = tuple(dict.fromkeys(page for page, _ in pieces))
        locations.append(StatementLocation(statement, basis, pdf_pages, pieces))
    return locations


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