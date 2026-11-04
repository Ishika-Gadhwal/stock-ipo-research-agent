"""Assemble the final markdown report.

Every number in the figures table comes from code. The analyst's notes are written
by an LLM, so they are labelled as such and checked against the extracted figures.
"""

from __future__ import annotations

from stock_ipo_research_agent.models import AnalystNote, CompanyCandidate
from stock_ipo_research_agent.tools.financial_facts import FinancialFacts

DISCLAIMER = (
    "Educational research only. Not investment advice. "
    "Not a SEBI-registered research service."
)


def empty_facts() -> FinancialFacts:
    """No extracted figures. Used to check notes when nothing could be extracted."""
    return FinancialFacts(
        source_url="", document_sha256="", total_pages=0,
        identity_evidence=[], figures=[], problems=[],
    )


def figures_table(facts: FinancialFacts) -> str:
    unit = facts.figures[0].unit
    lines = [
        f"| Basis | Item | Year ended | Value ({unit}) | PDF page |",
        "|---|---|---|---|---|",
    ]
    for f in facts.figures:
        star = " *" if f.starred else ""
        item = f.key.replace("_", " ").capitalize()
        lines.append(
            f"| {f.basis.capitalize()} | {item} | {f.period}{star} | {f.value:,} | {f.pdf_page} |"
        )
    return "\n".join(lines)


def build_report(
    *,
    identity: CompanyCandidate,
    sources_table: str,
    rejected_urls: list[str],
    not_found: list[str],
    facts: FinancialFacts | None,
    facts_problem: str | None,
    note: AnalystNote | None,
    unverified_numbers: list[str],
) -> str:
    lines = [
        f"# Research notes: {identity.legal_name}",
        "",
        f"NSE: {identity.nse_symbol} | BSE: {identity.bse_code} | ISIN: {identity.isin}",
        "",
        f"*{DISCLAIMER}*",
        "",
        "## Sources found by search",
        "",
        sources_table,
    ]
    if rejected_urls:
        lines += ["", "Rejected URLs (not found in any search result):", ""]
        lines += [f"- {url}" for url in rejected_urls]
    if not_found:
        lines += ["", "Not found by the source finder:", ""]
        lines += [f"- {item}" for item in not_found]

    lines += ["", "## Figures from the annual report (extracted by code)", ""]
    if facts is not None and facts.figures:
        lines += [
            f"Document: {facts.source_url} ({facts.total_pages} pages, "
            f"SHA-256 {facts.document_sha256[:12]})",
            "",
            figures_table(facts),
        ]
        if any(f.starred for f in facts.figures):
            lines += [
                "",
                "\\* This column's header carries an asterisk in the report. "
                "Read the report's footnote before calling it restated.",
            ]
    else:
        lines.append("No figures were extracted.")
    if facts is not None and facts.problems:
        lines += ["", "Could not extract:", ""]
        lines += [f"- {p}" for p in facts.problems]
    if facts_problem:
        lines += ["", f"Reason: {facts_problem}"]

    lines += ["", "## Analyst notes (written by an LLM; check against the table above)", ""]
    if note is None:
        lines.append("The analyst returned no notes.")
    else:
        lines.append(note.notes)
        lines.append("")
        if unverified_numbers:
            lines.append(
                "**Warning:** these numbers appear in the notes but were not extracted "
                "by code: " + ", ".join(unverified_numbers)
            )
        else:
            lines.append("Number check: no unverified numbers found in the notes.")
    return "\n".join(lines) + "\n"