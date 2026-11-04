#!/usr/bin/env python
from pathlib import Path

from pydantic import BaseModel

from crewai.flow import Flow, listen, start

from stock_ipo_research_agent.crews.content_crew.content_crew import ContentCrew
from stock_ipo_research_agent.crews.identity_crew.identity_crew import IdentityCrew
from stock_ipo_research_agent.models import CompanyCandidate
from stock_ipo_research_agent.tools.search import get_search_client, reset_search_client
from stock_ipo_research_agent.tools.source_checks import build_source_table


class ResearchState(BaseModel):
    company: str = "Tata Motors"
    candidates: list[CompanyCandidate] = []
    identity: CompanyCandidate | None = None
    report: str = ""


class ResearchFlow(Flow[ResearchState]):

    @start()
    def prepare_request(self, crewai_trigger_payload: dict = None):
        reset_search_client()  # new run, so forget URLs from any earlier run
        if crewai_trigger_payload:
            self.state.company = crewai_trigger_payload.get(
                "company", self.state.company
            )
        print(f"Company: {self.state.company}")

    @listen(prepare_request)
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
                return
            print("Invalid choice, try again.")

    @listen(confirm_identity)
    def run_research(self):
        e = self.state.identity
        company = f"{e.legal_name} (NSE: {e.nse_symbol}, BSE: {e.bse_code}, ISIN: {e.isin})"
        result = ContentCrew().crew().kickoff(inputs={"company": company})
        selection = result.pydantic
        if selection is None:
            raise ValueError("The research step did not return a structured list of sources.")

        # The agent only picked URLs. Code fills in title, date and type from real search results.
        table, rejected = build_source_table(selection.urls, get_search_client())

        lines = [
            f"# Sources for {e.legal_name}",
            "",
            f"NSE: {e.nse_symbol} | BSE: {e.bse_code} | ISIN: {e.isin}",
            "",
            "## Sources found by search",
            "",
            table,
        ]
        if rejected:
            lines += ["", "## Rejected URLs (not found in any search result)", ""]
            lines += [f"- {url}" for url in rejected]
        if selection.not_found:
            lines += ["", "## Not found", ""]
            lines += [f"- {item}" for item in selection.not_found]
        self.state.report = "\n".join(lines) + "\n"

    @listen(run_research)
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