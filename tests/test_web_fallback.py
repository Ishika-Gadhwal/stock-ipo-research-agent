"""The unverified web fallback: number tracing, the report section, the crew setup."""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("SERPER_API_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_report import report  # noqa: E402

from stock_ipo_research_agent.crews.web_fallback_crew.web_fallback_crew import (  # noqa: E402
    WebFallbackCrew,
)
from stock_ipo_research_agent.models import WebSummary  # noqa: E402
from stock_ipo_research_agent.tools.numbers_check import (  # noqa: E402
    find_untraced_numbers,
    numbers_in,
)
from stock_ipo_research_agent.tools.search import SearchClient  # noqa: E402

CORPUS = "Revenue of \u20b91,48,819 crore in FY26. Profit 29,211.5 crore. Q3 results."


class UntracedNumberTests(unittest.TestCase):
    def test_numbers_in_skips_years_and_dates(self) -> None:
        tokens = [t for t, _ in numbers_in("In FY2025-26 on March 31, 2026 revenue was 1,234.5")]
        self.assertEqual(tokens, ["1,234.5"])

    def test_number_found_in_a_snippet_is_traced_even_if_grouped_differently(self) -> None:
        self.assertEqual(find_untraced_numbers("Revenue was 148,819 crore.", CORPUS), [])
        self.assertEqual(find_untraced_numbers("Profit 29,211.50.", CORPUS), [])

    def test_number_missing_from_every_snippet_is_flagged_once(self) -> None:
        text = "Revenue was 148,819 crore, up 12%, profit 5,000 and again 5,000."
        self.assertEqual(find_untraced_numbers(text, CORPUS), ["12", "5,000"])

    def test_empty_corpus_flags_everything(self) -> None:
        self.assertEqual(find_untraced_numbers("Profit was 90.", ""), ["90"])


class ClientTests(unittest.TestCase):
    def test_all_results_returns_every_snippet_seen(self) -> None:
        from unittest import mock

        session = mock.Mock()
        session.post.return_value.json.return_value = {
            "organic": [
                {"title": "A", "link": "https://a.example/x", "snippet": "one 1"},
                {"title": "B", "link": "https://b.example/y", "snippet": "two 2"},
            ]
        }
        client = SearchClient(api_key="k", session=session)
        client.search("q")
        self.assertEqual({r.snippet for r in client.all_results()}, {"one 1", "two 2"})


class WebSectionTests(unittest.TestCase):
    def test_section_is_absent_when_the_fallback_did_not_run(self) -> None:
        self.assertNotIn("UNVERIFIED", report())

    def test_section_shows_label_text_sources_and_clean_number_check(self) -> None:
        text = report(
            web_summary="Revenue was 1,234 crore.", web_sources=["https://news.example/a"],
            web_untraced=[],
        )
        self.assertIn("## Web search summary (UNVERIFIED)", text)
        self.assertIn("not from the annual report", text)
        self.assertIn("Revenue was 1,234 crore.", text)
        self.assertIn("- https://news.example/a", text)
        self.assertIn("This does not make it correct.", text)

    def test_untraced_numbers_and_missing_sources_are_called_out(self) -> None:
        text = report(web_summary="Profit 99.", web_sources=[], web_untraced=["99"])
        self.assertIn("**Warning:** these numbers do not appear in any search snippet", text)
        self.assertIn("No source URL could be confirmed", text)

    def test_a_note_alone_still_gets_the_unverified_heading(self) -> None:
        text = report(web_note="The web search fallback found nothing usable.")
        self.assertIn("## Web search summary (UNVERIFIED)", text)
        self.assertIn("found nothing usable", text)

    def test_summary_note_explains_a_missing_summary(self) -> None:
        text = report(summary=None, summary_note="the writer failed. RuntimeError: x")
        self.assertIn("No summary was written. Reason: the writer failed.", text)


class CrewTests(unittest.TestCase):
    def test_researcher_has_the_search_tool_and_checked_output(self) -> None:
        crew = WebFallbackCrew().crew()
        self.assertEqual(len(crew.tasks), 1)
        self.assertIs(crew.tasks[0].output_pydantic, WebSummary)
        self.assertEqual([t.name for t in crew.agents[0].tools], ["Source search"])
        self.assertIn("{company}", crew.tasks[0].description)


if __name__ == "__main__":
    unittest.main()
