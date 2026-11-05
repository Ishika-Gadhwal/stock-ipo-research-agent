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
    IdentityResult,
    Narrative,
    ReportChoice,
    SelectedSources,
)
from stock_ipo_research_agent.tools.financial_facts import extract_pl_facts  # noqa: E402

PAGES = ["cover", CONSOLIDATED_PAGE, STANDALONE_PAGE]
GOOD_SUMMARY = "Consolidated revenue from operations was 335,582 INR crore."


def fake_crew(output):
    """A stand-in for a crew class: .crew().kickoff() returns `output`."""
    holder = mock.Mock()
    holder.return_value.crew.return_value.kickoff.return_value = output
    return holder


def content_output(urls, report_url):
    return SimpleNamespace(
        tasks_output=[
            SimpleNamespace(pydantic=SelectedSources(urls=urls, not_found=[])),
            SimpleNamespace(pydantic=ReportChoice(report_url=report_url)),
        ]
    )


def writer_output(summary):
    return SimpleNamespace(tasks_output=[SimpleNamespace(pydantic=Narrative(summary=summary))])


def fake_extract(url, company):
    return extract_pl_facts(url, company, loader=FakeLoader(PAGES))


class FlowTests(unittest.TestCase):
    def run_flow(self, content, client=None, summary=GOOD_SUMMARY):
        client = client or client_that_saw()
        self.writer = fake_crew(writer_output(summary))
        identity = SimpleNamespace(pydantic=IdentityResult(candidates=[COMPANY]))
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            os.chdir(tmp)
            try:
                with mock.patch.object(main, "IdentityCrew", fake_crew(identity)), \
                     mock.patch.object(main, "ContentCrew", fake_crew(content)), \
                     mock.patch.object(main, "NarrativeCrew", self.writer), \
                     mock.patch.object(main, "get_search_client", return_value=client), \
                     mock.patch.object(main, "reset_search_client"), \
                     mock.patch.object(main, "extract_pl_facts", side_effect=fake_extract), \
                     mock.patch("builtins.input", return_value="1"):
                    main.ResearchFlow().kickoff()
                return Path("output/report.md").read_text(encoding="utf-8")
            finally:
                os.chdir(previous)

    def test_happy_path_builds_a_report_with_code_made_figures(self) -> None:
        text = self.run_flow(content_output([URL], URL))
        self.assertIn("# Research notes: Test Motors Limited", text)
        self.assertIn("| Consolidated | Total revenue from operations | March 31, 2026 | 335,582 | 2 |", text)
        self.assertIn("## Summary", text)
        self.assertIn(GOOD_SUMMARY, text)
        self.assertIn("no unverified numbers", text)
        self.assertIn("official", text)  # label assigned by code from the allowlist

    def test_writer_only_receives_verified_figures_and_the_company_name(self) -> None:
        self.run_flow(content_output([URL], URL))
        inputs = self.writer.return_value.crew.return_value.kickoff.call_args.kwargs["inputs"]
        self.assertEqual(inputs["company"], "Test Motors Limited")
        self.assertIn("335,582 INR crore | PDF page 2", inputs["facts_text"])

    def test_invented_number_in_the_summary_is_flagged(self) -> None:
        text = self.run_flow(
            content_output([URL], URL), summary="Revenue was 335,582 crore, up 8.3%."
        )
        self.assertIn("**Warning:**", text)
        self.assertIn("8.3", text)

    def test_url_the_picker_made_up_is_never_read_and_code_falls_back(self) -> None:
        text = self.run_flow(content_output([URL], "https://made-up.example/ar.pdf"))
        self.assertIn("not returned by any search", text)
        self.assertIn("Fell back to an annual report PDF found by search", text)
        self.assertIn("| Consolidated | Total revenue from operations | March 31, 2026 | 335,582 | 2 |", text)
        self.assertIn("Note:", text)

    def test_picker_without_a_url_falls_back_to_a_search_result(self) -> None:
        text = self.run_flow(content_output([URL], None))
        self.assertIn("did not select an annual report URL", text)
        self.assertIn("Fell back to an annual report PDF found by search", text)
        self.assertIn("335,582", text)

    def test_no_annual_report_pdf_anywhere_means_no_figures_and_no_writer_call(self) -> None:
        page = "https://example.com/investor-relations"
        text = self.run_flow(content_output([page], None), client=client_that_saw(page))
        self.assertIn("No figures were extracted.", text)
        self.assertIn("Reason:", text)
        self.assertIn("No summary was written.", text)
        self.assertNotIn("| Basis |", text)
        self.writer.assert_not_called()

    def test_source_url_that_no_search_returned_is_rejected(self) -> None:
        text = self.run_flow(content_output([URL, "https://invented.example/x"], URL))
        self.assertIn("Rejected URLs", text)
        self.assertIn("https://invented.example/x", text)


if __name__ == "__main__":
    unittest.main()