#!/usr/bin/env python
from pathlib import Path

from pydantic import BaseModel

from crewai.flow import Flow, listen, start ,or_, router

from stock_ipo_research_agent.crews.content_crew.content_crew import ContentCrew
from stock_ipo_research_agent.crews.identity_crew.identity_crew import IdentityCrew
from stock_ipo_research_agent.models import CompanyCandidate
from stock_ipo_research_agent.report import DISCLAIMER, build_report
from stock_ipo_research_agent.tools.financial_facts import (
    extract_pl_facts,
    reset_company,
    set_company,
)
from stock_ipo_research_agent.tools.facts_selection import find_facts
from stock_ipo_research_agent.tools.numbers_check import (
    find_numbers_near_quarters,
    find_unverified_numbers,
    find_untraced_numbers,
)
from stock_ipo_research_agent.tools.search import get_search_client, reset_search_client
from stock_ipo_research_agent.tools.source_checks import build_source_table

from stock_ipo_research_agent.crews.narrative_crew.narrative_crew import NarrativeCrew
from stock_ipo_research_agent.crews.web_fallback_crew.web_fallback_crew import WebFallbackCrew
from stock_ipo_research_agent.tools.narrative_input import build_writer_input


MODES = ("stock", "ipo")


def _kickoff(crew_class, inputs: dict):
    """Run a summary crew. Returns (output, None) or (None, short error text).

    WHY: a failed summary (for example a Gemini 503) must never lose the report, and
    above all must never lose figures that code already extracted.
    """
    try:
        return crew_class().crew().kickoff(inputs=inputs), None
    except Exception as error:  # noqa: BLE001
        return None, f"{type(error).__name__}: {str(error)[:200]} (see the terminal for details)"


def normalise_mode(value: str | None) -> str:
    """Return 'stock' or 'ipo'. Anything else is an error, never a silent default."""
    mode = (value or "stock").strip().lower()
    if mode not in MODES:
        raise ValueError(f"Unknown mode {value!r}. Use one of: {', '.join(MODES)}.")
    return mode


class ResearchState(BaseModel):
    company: str = "Tata Motors"
    mode: str = "stock"
    candidates: list[CompanyCandidate] = []
    identity: CompanyCandidate | None = None
    report: str = ""


class ResearchFlow(Flow[ResearchState]):

    @start()
    def prepare_request(self, crewai_trigger_payload: dict = None):
        reset_search_client()  # new run, so forget URLs from any earlier run
        reset_company()
        if crewai_trigger_payload:
            self.state.company = crewai_trigger_payload.get(
                "company", self.state.company
            )
            self.state.mode = normalise_mode(crewai_trigger_payload.get("mode"))
        print(f"Company: {self.state.company} | Mode: {self.state.mode}")

    @router(prepare_request)
    def choose_path(self):
        # Code decides the path, never the LLM.
        return self.state.mode

    @listen("ipo")
    def ipo_stub(self):
        # WHY: the IPO path is built in a later step. Say so plainly instead of guessing.
        self.state.report = (
            f"# IPO research: {self.state.company}\n\n*{DISCLAIMER}*\n\n"
            "The IPO path is not built yet. No research was done.\n"
        )

    @listen("stock")
    def resolve_identity(self):        
        result = IdentityCrew().crew().kickoff(
            inputs={"company": self.state.company}
        )
        self.state.candidates = result.pydantic.candidates

    @listen(resolve_identity)
    def confirm_identity(self):
        candidates = self.state.candidates
        if not candidates:
            raise ValueError("No matching companies found. Try a more specific name.")

        print("\nPossible matches:")
        for i, c in enumerate(candidates, start=1):
            print(f"{i}. {c.legal_name} | NSE: {c.nse_symbol} | BSE: {c.bse_code} | ISIN: {c.isin}")
            print(f"   {c.business}")
            print(f"   Source: {c.source_url}")
            if not get_search_client().was_seen(c.source_url):
                print("   [warning: this source URL was not found in any search result]")

        if len(candidates) == 1:
            print(
                "\nNote: only one match found. If you expected more "
                "(for example after a rename or demerger), press q and "
                "try a more specific name."
            )

        while True:
            choice = input(f"\nChoose 1-{len(candidates)}, or q to quit: ").strip().lower()
            if choice == "q":
                raise SystemExit("Stopped by user.")
            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                self.state.identity = candidates[int(choice) - 1]
                # The report tool reads this, so the LLM can never pick the company.
                set_company(self.state.identity)
                return
            print("Invalid choice, try again.")

    @listen(confirm_identity)
    def run_research(self):
        e = self.state.identity
        company = f"{e.legal_name} (NSE: {e.nse_symbol}, BSE: {e.bse_code}, ISIN: {e.isin})"
        result = ContentCrew().crew().kickoff(inputs={"company": company})

        # Task 1 = source finder, task 2 = report picker.
        selection = result.tasks_output[0].pydantic
        choice = result.tasks_output[1].pydantic
        if selection is None:
            raise ValueError("The research step did not return a structured list of sources.")

        client = get_search_client()
        sources_table, rejected = build_source_table(selection.urls, client)

        # Figures come from code. The picker chooses the report; if that fails,
        # code falls back to annual-report PDFs found by search.
        report_url = choice.report_url if choice else None
        facts, facts_notes = find_facts(client, e, report_url, extract=extract_pl_facts)
        facts_problem = " ".join(facts_notes) or None

        # The writer runs only when code extracted figures. Its numbers are checked.
        summary: str | None = None
        summary_note: str | None = None
        unverified: list[str] = []
        if facts is not None and facts.figures:
            written, error = _kickoff(
                NarrativeCrew,
                {"company": e.legal_name, "facts_text": build_writer_input(facts)},
            )
            if error:
                summary_note = f"the writer failed. {error}"
            else:
                narrative = written.tasks_output[0].pydantic
                summary = narrative.summary if narrative else None
                if summary:
                    unverified = find_unverified_numbers(summary, facts)

        # Only when code could not read ANY figures: a web-search summary, labelled
        # UNVERIFIED, so the report is never empty. Numbers are traced to search snippets.
        web_summary: str | None = None
        web_sources: list[str] = []
        web_untraced: list[str] = []
        web_quarter: list[str] = []
        web_note: str | None = None
        if facts is None or not facts.figures:
            researched, error = _kickoff(WebFallbackCrew, {"company": company})
            if error:
                web_note = f"The web search fallback could not run. {error}"
            else:
                found = researched.tasks_output[0].pydantic
                if found is not None and found.summary.strip():
                    web_summary = found.summary
                    web_sources = [url for url in found.source_urls if client.was_seen(url)]
                    snippets = client.all_snippets()
                    web_untraced = find_untraced_numbers(web_summary, "\n".join(snippets))
                    web_quarter = find_numbers_near_quarters(web_summary, snippets)
                else:
                    web_note = "The web search fallback found nothing usable."

        self.state.report = build_report(
            identity=e,
            sources_table=sources_table,
            rejected_urls=rejected,
            not_found=selection.not_found,
            facts=facts,
            facts_problem=facts_problem,
            summary=summary,
            unverified_numbers=unverified,
            summary_note=summary_note,
            web_summary=web_summary,
            web_sources=web_sources,
            web_untraced=web_untraced,
            web_note=web_note,
            web_quarter=web_quarter,
        )


    @listen(or_(run_research, ipo_stub))
    def save_report(self):
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        path = output_dir / "report.md"
        path.write_text(self.state.report, encoding="utf-8")
        print(f"Report saved to {path}")
        return self.state.report


def kickoff():
    ResearchFlow().kickoff()


def plot():
    ResearchFlow().plot()


def run_with_trigger():
    """Run the flow with a JSON trigger payload."""
    import json
    import sys

    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    try:
        ResearchFlow().kickoff({"crewai_trigger_payload": trigger_payload})
    except Exception as e:
        raise Exception(f"An error occurred while running the flow with trigger: {e}")


if __name__ == "__main__":
    kickoff()
