"""Assemble the final markdown report.

Every number in the figures table comes from code. The analyst's notes are written
by an LLM, so they are labelled as such and checked against the extracted figures.
"""

from __future__ import annotations

from datetime import date

from stock_ipo_research_agent.models import CompanyCandidate, IpoView
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
            f"| {f.basis.capitalize()} | {item} | {f.period}{star} | {f.value:,} | {f.page_label} |"
        )
    return "\n".join(lines)


def data_status(facts: FinancialFacts | None, web_summary: str | None) -> str:
    """One line a reader can trust at a glance: where the numbers in this report come from."""
    if facts is not None and facts.figures:
        note = " (some statements could not be read)" if facts.problems else ""
        return "verified figures extracted from the annual report" + note
    if web_summary:
        return "no verified figures; an UNVERIFIED web summary is included"
    return "no figures found"


def build_report(
    *,
    identity: CompanyCandidate,
    sources_table: str,
    rejected_urls: list[str],
    not_found: list[str],
    facts: FinancialFacts | None,
    facts_problem: str | None,
    summary: str | None,
    unverified_numbers: list[str],
    summary_note: str | None = None,
    web_summary: str | None = None,
    web_sources: list[str] | None = None,
    web_untraced: list[str] | None = None,
    web_note: str | None = None,
    web_quarter: list[str] | None = None,
    report_date: str | None = None,
) -> str:
    lines = [
        f"# Research notes: {identity.legal_name}",
        "",
        f"NSE: {identity.nse_symbol} | BSE: {identity.bse_code} | ISIN: {identity.isin}",
        "",
        f"*{DISCLAIMER}*",
        "",
        f"Report date: {report_date or date.today().isoformat()} | "
        f"Data status: {data_status(facts, web_summary)}",
        "",
        "## Sources found by search",
        "",
        sources_table,
        "",
        '*"official" means the link is on an exchange or SEBI website. '
        "It does not prove the document belongs to this company.*",
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
        label = "Note" if facts is not None and facts.figures else "Reason"
        lines += ["", f"{label}: {facts_problem}"]

    lines += ["", "## Summary (written by an LLM; check against the table above)", ""]
    if summary is None:
        lines.append("No summary was written." + (f" Reason: {summary_note}" if summary_note else ""))
    else:
        lines.append(summary)
        lines.append("")
        if unverified_numbers:
            lines.append(
                "**Warning:** these numbers appear in the summary but were not extracted "
                "by code: " + ", ".join(unverified_numbers)
            )
        else:
            lines.append("Number check: no unverified numbers found in the summary.")

    if web_summary or web_note:
        lines += [
            "",
            "## Web search summary (UNVERIFIED)",
            "",
            "**UNVERIFIED: this text comes from web search snippets, not from the annual "
            "report. Check every statement against the sources before relying on it.**",
            "",
        ]
        if web_summary:
            lines += [web_summary, ""]
            if web_sources:
                lines += ["Sources (each was returned by a search):", ""]
                lines += [f"- {url}" for url in web_sources]
            else:
                lines.append("No source URL could be confirmed against the search results.")
            lines.append("")
            if web_untraced:
                lines.append(
                    "**Warning:** these numbers do not appear in any search snippet from this "
                    "run: " + ", ".join(web_untraced)
                )
            else:
                lines.append(
                    "Number check: every number in this text appears in a search snippet. "
                    "This does not make it correct."
                )
            if web_quarter:
                lines += [
                    "",
                    "**Check the period:** these numbers also appear in a search snippet that "
                    "mentions a quarter or half-year, so they may not be annual figures: "
                    + ", ".join(web_quarter),
                ]
        if web_note:
            lines += ["", web_note]
    return "\n".join(lines) + "\n"


_LEAN_TEXT = {
    "apply": "Leaning towards applying",
    "neutral": "Undecided: the news is not clear enough either way",
    "avoid": "Leaning towards skipping",
}


def effective_lean(view: IpoView, sources: list[tuple[str, str | None, str]]) -> tuple[str, str, str | None]:
    """The lean to show: (lean, confidence, note).

    Code, not the LLM, has the last word. With no source confirmed against the real
    search results, a lean would rest on nothing, so it becomes neutral with low confidence.
    """
    if not sources:
        return "neutral", "low", "No source URL could be confirmed, so no lean is given."
    return view.lean, view.confidence, None


def build_ipo_report(
    company: str,
    view: IpoView | None,
    sources: list[tuple[str, str | None, str]],
    untraced: list[str],
    note: str | None = None,
    report_date: str | None = None,
) -> str:
    """IPO report. sources are (url, date as shown by search, type) for URLs that were
    really returned by a search. Everything here is UNVERIFIED."""
    day = report_date or date.today().isoformat()
    lines = [
        f"# IPO research: {company}",
        "",
        f"*{DISCLAIMER}*",
        "",
        f"Report date: {day} | Data status: "
        + (
            "UNVERIFIED, written by an LLM from recent web search snippets. No offer document was read"
            if view is not None
            else "no usable news found"
        ),
        "",
        "**UNVERIFIED: this text comes from web search snippets, not from the offer document "
        "(DRHP or RHP). Check every statement against the sources and the RHP before relying "
        "on it.**",
    ]
    if view is None:
        lines += ["", note or "No IPO news could be summarised."]
        return "\n".join(lines) + "\n"

    lean, confidence, lean_note = effective_lean(view, sources)
    lines += [
        "",
        "## Lean from recent news (not advice)",
        "",
        f"**{_LEAN_TEXT[lean]}** (confidence: {confidence})",
    ]
    if lean_note:
        lines += ["", lean_note]
    elif view.lean_reason.strip():
        lines += ["", view.lean_reason.strip()]
    lines += [
        "",
        "*This is a reading of news snippets. It cannot know your goals, finances or risk "
        "tolerance, and the final price band can differ from older articles. Read the RHP "
        "and decide for yourself.*",
        "",
        "## Summary",
        "",
        view.summary.strip(),
        "",
        "## Pros (from the news)",
        "",
    ]
    lines += [f"- {point}" for point in view.pros] or ["- none found"]
    lines += ["", "## Cons and risks (from the news)", ""]
    lines += [f"- {point}" for point in view.cons] or ["- none found"]
    lines += ["", "## Sources (each was returned by a search)", ""]
    if sources:
        lines += ["| URL | Date shown by search | Type |", "|---|---|---|"]
        lines += [f"| {url} | {when or 'Not stated'} | {kind} |" for url, when, kind in sources]
    else:
        lines.append("No source URL could be confirmed against the search results.")
    if untraced:
        lines += [
            "",
            "**Warning:** these numbers do not appear in any search snippet from this run: "
            + ", ".join(untraced),
        ]
    else:
        lines += [
            "",
            "Number check: every number in this text appears in a search snippet. "
            "This does not make it correct.",
        ]
    if note:
        lines += ["", note]
    return "\n".join(lines) + "\n"
