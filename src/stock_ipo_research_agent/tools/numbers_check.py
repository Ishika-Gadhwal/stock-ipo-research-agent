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