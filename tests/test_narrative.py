import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("SERPER_API_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent))  # reuse the other tests' fixtures

from test_financial_facts import COMPANY, URL, FakeLoader  # noqa: E402
from test_statement_extractor import CONSOLIDATED_PAGE, STANDALONE_PAGE  # noqa: E402

from stock_ipo_research_agent.crews.narrative_crew.narrative_crew import NarrativeCrew  # noqa: E402
from stock_ipo_research_agent.models import Narrative  # noqa: E402
from stock_ipo_research_agent.report import empty_facts  # noqa: E402
from stock_ipo_research_agent.tools.financial_facts import extract_pl_facts  # noqa: E402
from stock_ipo_research_agent.tools.narrative_input import build_writer_input  # noqa: E402
from stock_ipo_research_agent.tools.numbers_check import find_unverified_numbers  # noqa: E402

FACTS = extract_pl_facts(
    URL, COMPANY, loader=FakeLoader(["cover", CONSOLIDATED_PAGE, STANDALONE_PAGE])
)


class WriterInputTests(unittest.TestCase):
    def test_lists_every_figure_with_basis_and_page(self) -> None:
        text = build_writer_input(FACTS)
        self.assertIn("Consolidated | Total revenue from operations | year ended March 31, 2026", text)
        self.assertIn("335,582 INR crore | PDF page 2", text)
        self.assertIn("Standalone | Total revenue from operations", text)
        self.assertIn("-1,377 INR crore", text)

    def test_marks_starred_columns(self) -> None:
        self.assertIn("marked with an asterisk", build_writer_input(FACTS))

    def test_hides_numbers_the_writer_does_not_need(self) -> None:
        text = build_writer_input(FACTS)
        self.assertNotIn(FACTS.document_sha256[:12], text)
        self.assertNotIn("line:", text)
        self.assertNotIn("Pages:", text)
        self.assertNotIn("Identity check", text)

    def test_no_figures_gives_one_plain_sentence_without_reason_text(self) -> None:
        for facts in (None, empty_facts()):
            text = build_writer_input(facts)
            self.assertEqual(text, "No figures were extracted from an annual report.")

    def test_problems_show_only_the_basis_name(self) -> None:
        facts = FACTS.model_copy(
            update={"problems": ["standalone: could not extract safely (first 15 pages odd)"]}
        )
        text = build_writer_input(facts)
        self.assertIn("Could not be extracted (say 'not found'): standalone", text)
        self.assertNotIn("15", text)

    def test_copying_the_input_passes_the_number_check(self) -> None:
        summary = "Consolidated revenue from operations was 335,582 INR crore (PDF page 2)."
        self.assertEqual(find_unverified_numbers(summary, FACTS), [])


class NarrativeCrewTests(unittest.TestCase):
    def test_writer_has_no_tools_and_one_task_with_checked_output(self) -> None:
        crew = NarrativeCrew().crew()
        self.assertEqual(len(crew.agents), 1)
        self.assertEqual(len(crew.tasks), 1)
        self.assertEqual(crew.agents[0].tools, [])
        self.assertIs(crew.tasks[0].output_pydantic, Narrative)

    def test_task_takes_company_and_facts_as_inputs(self) -> None:
        description = NarrativeCrew().crew().tasks[0].description
        self.assertIn("{company}", description)
        self.assertIn("{facts_text}", description)

    def test_narrative_model_holds_a_summary(self) -> None:
        self.assertEqual(Narrative(summary="x").summary, "x")


if __name__ == "__main__":
    unittest.main()
