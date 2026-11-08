"""Find numbers in LLM-written text that the code did not extract.

Rule: every number in the narrative must be one of the extracted figures (or one of
their PDF page numbers). Anything else, including a number the LLM computed itself
(a percentage, a rounded value), is reported as unverified. Years, fiscal-year
labels and dates are ignored. The check only reports; it never edits the text.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from stock_ipo_research_agent.tools.financial_facts import FinancialFacts

_MONTH = (
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
)
# Removed before looking for numbers: dates, year ranges such as 2025-26, plain years.
_IGNORED = [
    re.compile(r"\bFY\s?\d{2,4}(?:\s*[-\u2013/]\s*\d{2,4})?", re.IGNORECASE),  # FY26, FY2025-26
    re.compile(rf"\b{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?\b", re.IGNORECASE),
    re.compile(r"\b(?:19|20)\d{2}\s*[-\u2013/]\s*\d{2,4}\b"),
    re.compile(r"\b(?:19|20)\d{2}\b"),
]
# A number glued to a letter (Q3) is skipped by the lookbehind and lookahead below.
_NUMBER = re.compile(r"(?<![\w.])\(?-?\d[\d,]*(?:\.\d+)?\)?(?!\w)")


def _to_decimal(token: str) -> Decimal | None:
    cleaned = token.strip("()").lstrip("-").replace(",", "").rstrip(".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def find_unverified_numbers(text: str, facts: FinancialFacts) -> list[str]:
    """Numbers in text that are not an extracted figure or its page number."""
    allowed = {abs(f.value) for f in facts.figures}
    allowed |= {Decimal(f.pdf_page) for f in facts.figures}

    cleaned = text
    for pattern in _IGNORED:
        cleaned = pattern.sub(" ", cleaned)

    flagged: list[str] = []
    for match in _NUMBER.finditer(cleaned):
        token = match.group(0).strip().rstrip(",")
        value = _to_decimal(token)
        if value is None or value in allowed or token in flagged:
            continue
        flagged.append(token)
    return flagged


def numbers_in(text: str) -> list[tuple[str, Decimal]]:
    """Every number in text as (token, value). Dates, years and fiscal-year labels are skipped."""
    cleaned = text
    for pattern in _IGNORED:
        cleaned = pattern.sub(" ", cleaned)
    found = []
    for match in _NUMBER.finditer(cleaned):
        token = match.group(0).strip().rstrip(",")
        value = _to_decimal(token)
        if value is not None:
            found.append((token, value))
    return found


def find_untraced_numbers(text: str, corpus: str) -> list[str]:
    """Numbers in text that appear nowhere in corpus (the search snippets of this run).

    This is a weaker check than find_unverified_numbers. It shows a number was
    printed in a search result. It does not show the number is right.
    """
    traced = {abs(value) for _, value in numbers_in(corpus)}
    flagged: list[str] = []
    for token, value in numbers_in(text):
        if abs(value) not in traced and token not in flagged:
            flagged.append(token)
    return flagged


_QUARTER_WORDS = re.compile(r"\bQ[1-4]\b|quarter|half[- ]?year|\bH[12]\b|nine months", re.IGNORECASE)


def find_numbers_near_quarters(text: str, snippets: list[str]) -> list[str]:
    """Numbers in text that also appear in a snippet mentioning a quarter or half-year.

    Such a number may be a quarterly figure that the writer labelled as annual. The
    check only asks the reader to confirm the period. It never says the number is wrong.
    """
    quarterly: set[Decimal] = set()
    for snippet in snippets:
        if _QUARTER_WORDS.search(snippet):
            quarterly |= {abs(value) for _, value in numbers_in(snippet)}
    flagged: list[str] = []
    for token, value in numbers_in(text):
        if abs(value) in quarterly and token not in flagged:
            flagged.append(token)
    return flagged
