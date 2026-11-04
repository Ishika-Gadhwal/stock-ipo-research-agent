"""Build the sources table in CODE from real search results.

The LLM only picks URLs. Title, date and source type come from the search results
the tool actually returned. A URL that no search returned is rejected, not shown.
"""

from __future__ import annotations

from stock_ipo_research_agent.tools.search import SearchClient, normalise_url


def _cell(text: str) -> str:
    """Keep a value from breaking the markdown table."""
    return " ".join(text.replace("|", "/").split())


def build_source_table(urls: list[str], client: SearchClient) -> tuple[str, list[str]]:
    """Return (markdown table, rejected URLs). Duplicates appear once."""
    rows: list[str] = []
    rejected: list[str] = []
    done: set[str] = set()
    for url in urls:
        key = normalise_url(url)
        if key in done:
            continue
        done.add(key)
        result = client.lookup(url)
        if result is None:
            rejected.append(url)
            continue
        rows.append(
            f"| {_cell(result.title)} | {result.url} | {result.source_type} "
            f"| {result.date or 'Not stated'} |"
        )
    if not rows:
        return "No verified sources found.", rejected
    header = "| Source | URL | Type | Date |\n|---|---|---|---|"
    return header + "\n" + "\n".join(rows), rejected