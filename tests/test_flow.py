"""Runs the whole Flow with fake crews and a fake PDF reader. No LLM, no network, no PDF."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # reuse the other tests' fixtures
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")  # no "share trace?" prompt in tests

from test_financial_facts import COMPANY, URL, FakeLoader, client_that_saw  # noqa: E402
from test_statement_extractor import CONSOLIDATED_PAGE, STANDALONE_PAGE  # noqa: E402

from stock_ipo_research_agent import main  # noqa: E402
from stock_ipo_research_agent.models import (  # noqa: E402
    AnalystNote,
    IdentityResult,
    SelectedSources,
)
from stock_ipo_research_agent.tools.financial_facts import extract_pl_facts  # noqa: E402

PAGES = ["cover", CONSOLIDATED_PAGE, STANDALONE_PAGE]


def fake_crew(output):
    """A stand-in for IdentityCrew / ContentCrew: .crew().kickoff() returns `output`."""
    holder = mock.Mock()
    holder.return_value.crew.return_value.kickoff.return_value = output
    return holder


def content_output(urls, note):
    return SimpleNamespace(
        tasks_output=[
            SimpleNamespace(pydantic=SelectedSources(urls=urls, not_found=[])),
            SimpleNamespace(pydantic=note),
        ]
    )


def fake_extract(url, company):
    return extract_pl_facts(url, company, loader=FakeLoader(PAGES))


class FlowTests(unittest.TestCase):
    def run_flow(self, content, client=None):
        client = client or client_that_saw()
        identity = SimpleNamespace(pydantic=IdentityResult(candidates=[COMPANY]))
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            os.chdir(tmp)
            try:
                with mock.patch.object(main, "IdentityCrew", fake_crew(identity)), \
                     mock.patch.object(main, "ContentCrew", fake_crew(content)), \
                     mock.patch.object(main, "get_search_client", return_value=client), \
                     mock.patch.object(main, "reset_search_client"), \
                     mock.patch.object(main, "extract_pl_facts", side_effect=fake_extract), \
                     mock.patch("builtins.input", return_value="1"):
                    main.ResearchFlow().kickoff()
                return Path("output/report.md").read_text(encoding="utf-8")
            finally:
                os.chdir(previous)

    def test_happy_path_builds_a_report_with_code_made_figures(self) -> None:
        note = AnalystNote(report_url=URL, notes="Consolidated revenue was 335,582 crore.")
        text = self.run_flow(content_output([URL], note))
        self.assertIn("# Research notes: Test Motors Limited", text)
        self.assertIn("| Consolidated | Total revenue from operations | March 31, 2026 | 335,582 | 2 |", text)
        self.assertIn("no unverified numbers", text)
        self.assertIn("official", text)  # label assigned by code from the allowlist

    def test_invented_number_in_the_notes_is_flagged(self) -> None:
        note = AnalystNote(report_url=URL, notes="Revenue was 335,582 crore, up 8.3%.")
        text = self.run_flow(content_output([URL], note))
        self.assertIn("**Warning:**", text)
        self.assertIn("8.3", text)

    def test_url_the_analyst_made_up_is_never_read_and_code_falls_back(self) -> None:
        note = AnalystNote(report_url="https://made-up.example/ar.pdf", notes="No numbers.")
        text = self.run_flow(content_output([URL], note))
        self.assertIn("not returned by any search", text)
        self.assertIn("Fell back to an annual report PDF found by search", text)
        self.assertIn("| Consolidated | Total revenue from operations | March 31, 2026 | 335,582 | 2 |", text)
        self.assertIn("Note:", text)

    def test_analyst_without_a_url_falls_back_to_a_search_result(self) -> None:
        note = AnalystNote(report_url=None, notes="Could not find the annual report.")
        text = self.run_flow(content_output([URL], note))
        self.assertIn("did not select an annual report URL", text)
        self.assertIn("Fell back to an annual report PDF found by search", text)
        self.assertIn("335,582", text)

    def test_no_annual_report_pdf_anywhere_means_no_figures(self) -> None:
        page = "https://example.com/investor-relations"
        note = AnalystNote(report_url=None, notes="Could not find the annual report.")
        text = self.run_flow(content_output([page], note), client=client_that_saw(page))
        self.assertIn("No figures were extracted.", text)
        self.assertIn("Reason:", text)
        self.assertIn("did not select an annual report URL", text)
        self.assertNotIn("| Basis |", text)

    def test_source_url_that_no_search_returned_is_rejected(self) -> None:
        note = AnalystNote(report_url=URL, notes="Ok.")
        text = self.run_flow(content_output([URL, "https://invented.example/x"], note))
        self.assertIn("Rejected URLs", text)
        self.assertIn("https://invented.example/x", text)


if __name__ == "__main__":
    unittest.main()
