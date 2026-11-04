"""Build the text the report writer reads. Pure code, no LLM.

The writer sees only the verified figures (basis, item, year, value, unit, page).
It does NOT see the SHA, the page count, source lines, or error messages, because
those contain numbers the writer might repeat and the number check would then flag.
"""

from __future__ import annotations

from stock_ipo_research_agent.tools.financial_facts import FinancialFacts

_BASES = ("consolidated", "standalone")


def _name(key: str) -> str:
    return key.replace("_", " ").capitalize()


def build_writer_input(facts: FinancialFacts | None) -> str:
    if facts is None or not facts.figures:
        return "No figures were extracted from an annual report."

    lines = ["Verified figures (copy them exactly, with the PDF page):"]
    for f in facts.figures:
        star = " (comparative column, marked with an asterisk in the report)" if f.starred else ""
        lines.append(
            f"- {f.basis.capitalize()} | {_name(f.key)} | year ended {f.period}{star} "
            f"| {f.value:,} {f.unit} | PDF page {f.pdf_page}"
        )

    # Only the basis name of each problem, never the error text (it can contain numbers).
    missing = []
    for problem in facts.problems:
        basis = problem.split(":", 1)[0].strip().lower()
        if basis in _BASES and basis not in missing:
            missing.append(basis)
    if missing:
        lines += ["", "Could not be extracted (say 'not found'): " + ", ".join(missing)]
    return "\n".join(lines)
