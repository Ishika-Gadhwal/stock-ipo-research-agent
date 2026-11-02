#!/usr/bin/env python
from pathlib import Path

from pydantic import BaseModel

from crewai.flow import Flow, listen, start

from stock_ipo_research_agent.crews.content_crew.content_crew import ContentCrew


class ResearchState(BaseModel):
    company: str = "Tata Motors"
    report: str = ""


class ResearchFlow(Flow[ResearchState]):

    @start()
    def prepare_request(self, crewai_trigger_payload: dict = None):
        if crewai_trigger_payload:
            self.state.company = crewai_trigger_payload.get(
                "company", self.state.company
            )
        print(f"Company: {self.state.company}")

    @listen(prepare_request)
    def run_research(self):
        result = (
            ContentCrew()
            .crew()
            .kickoff(inputs={"company": self.state.company})
        )
        self.state.report = result.raw

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