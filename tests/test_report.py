import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # reuse the other tests' fixtures

from test_financial_facts import COMPANY, URL, FakeLoader  # noqa: E402
from test_statement_extractor import CONSOLIDATED_PAGE, STANDALONE_PAGE  # noqa: E402

from stock_ipo_research_agent.report import build_report, empty_facts  # noqa: E402
from stock_ipo_research_agent.tools.financial_facts import extract_pl_facts  # noqa: E402

FACTS = extract_pl_facts(
    URL, COMPANY, loader=FakeLoader(["cover", CONSOLIDATED_PAGE, STANDALONE_PAGE])
)
TABLE = "| Source | URL | Type | Date |\n|---|---|---|---|\n| AR | https://x | official | Not stated |"


def report(**overrides):
    args = dict(
        identity=COMPANY, sources_table=TABLE, rejected_urls=[], not_found=[],
        facts=FACTS, facts_problem=None,
        summary="Consolidated revenue was 335,582 crore.",        
        unverified_numbers=[],
    )
    args.update(overrides)
    return build_report(**args)


class ReportTests(unittest.TestCase):
    def test_full_report_has_disclaimer_sources_figures_and_notes(self) -> None:
        text = report()
        self.assertIn("# Research notes: Test Motors Limited", text)
        self.assertIn("Not investment advice", text)
        self.assertIn("| AR | https://x | official | Not stated |", text)
        self.assertIn("| Consolidated | Total revenue from operations | March 31, 2026 | 335,582 | 2 |", text)
        self.assertIn("| Consolidated | Profit from continuing operations | March 31, 2026 | -1,377 | 2 |", text)
        self.assertIn("| Standalone | Total revenue from operations | March 31, 2026 | 57,859 | 3 |", text)
        self.assertIn("March 31, 2025 *", text)  # starred column is marked
        self.assertIn("asterisk", text)
        self.assertIn("written by an LLM", text)
        self.assertIn("no unverified numbers", text)

    def test_unverified_numbers_produce_a_warning(self) -> None:
        text = report(unverified_numbers=["8.3", "29,000"])
        self.assertIn("**Warning:**", text)
        self.assertIn("8.3, 29,000", text)
        self.assertNotIn("no unverified numbers", text)

    def test_no_facts_says_why_and_shows_no_table(self) -> None:
        text = report(facts=None, facts_problem="The analyst did not select an annual report URL.")
        self.assertIn("No figures were extracted.", text)
        self.assertIn("did not select an annual report URL", text)
        self.assertNotIn("| Basis |", text)

    def test_problems_are_listed(self) -> None:
        facts = extract_pl_facts(URL, COMPANY, loader=FakeLoader(["cover", CONSOLIDATED_PAGE]))
        text = report(facts=facts)
        self.assertIn("Could not extract:", text)
        self.assertIn("standalone", text)

    def test_optional_sections_only_appear_when_needed(self) -> None:
        self.assertNotIn("Rejected URLs", report())
        self.assertNotIn("Not found by the source finder", report())
        text = report(rejected_urls=["https://made-up.example"], not_found=["investor relations page"])
        self.assertIn("- https://made-up.example", text)
        self.assertIn("- investor relations page", text)

    def test_note_label_when_figures_exist_and_reason_label_when_they_do_not(self) -> None:
        with_figures = report(facts_problem="Fell back to a PDF found by search.")
        self.assertIn("Note: Fell back to a PDF found by search.", with_figures)
        self.assertNotIn("Reason:", with_figures)
        without = report(facts=None, facts_problem="Nothing found.")
        self.assertIn("Reason: Nothing found.", without)

    def test_missing_summary_is_stated(self) -> None:
        self.assertIn("No summary was written.", report(summary=None))
        
    def test_empty_facts_allow_no_numbers(self) -> None:
        self.assertEqual(empty_facts().figures, [])


if __name__ == "__main__":
    unittest.main()
