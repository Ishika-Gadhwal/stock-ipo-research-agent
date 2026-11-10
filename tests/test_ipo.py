"""IPO path: recent news in, pros/cons and a cautious lean out. No LLM, no network."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("SERPER_API_KEY", "dummy")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_flow import crashing_crew, fake_crew  # noqa: E402

from stock_ipo_research_agent import main  # noqa: E402
from stock_ipo_research_agent.crews.ipo_news_crew.ipo_news_crew import IpoNewsCrew  # noqa: E402
from stock_ipo_research_agent.models import IpoView  # noqa: E402
from datetime import date  # noqa: E402

from stock_ipo_research_agent.report import (  # noqa: E402
    absolute_date,
    build_ipo_report,
    effective_lean,
)
from stock_ipo_research_agent.tools.search import SearchClient  # noqa: E402

NEWS = "https://news.example/acme-ipo"
SNIPPET = "Acme IPO opens Nov 12. Price band 100 to 105 per share. Issue size 1,500 crore."
SOURCES = [(NEWS, "2 days ago", "unverified")]


def view(**changes):
    base = dict(
        summary="Acme IPO opens Nov 12 with a price band of 100 to 105.",
        pros=["Strong order book"], cons=["Rich valuation"], lean="apply",
        lean_reason="Demand looks strong but valuation is rich.", confidence="medium",
        source_urls=[NEWS],
    )
    base.update(changes)
    return IpoView(**base)


def client_with_news():
    session = mock.Mock()
    session.post.return_value.json.return_value = {
        "organic": [{"title": "Acme IPO", "link": NEWS, "snippet": SNIPPET, "date": "2 days ago"}]
    }
    client = SearchClient(api_key="k", session=session)
    client.search("Acme IPO news")
    return client


class LeanGuardTests(unittest.TestCase):
    def test_lean_is_kept_when_a_source_is_confirmed(self) -> None:
        self.assertEqual(effective_lean(view(), SOURCES), ("apply", "medium", None))

    def test_no_confirmed_source_forces_neutral_and_low_confidence(self) -> None:
        lean, confidence, note = effective_lean(view(lean="avoid", confidence="high"), [])
        self.assertEqual((lean, confidence), ("neutral", "low"))
        self.assertIn("No source URL could be confirmed", note)


class ReportTests(unittest.TestCase):
    def build(self, **overrides):
        args = dict(company="Acme", view=view(), sources=SOURCES, untraced=[], report_date="2026-11-08")
        args.update(overrides)
        return build_ipo_report(**args)

    def test_report_has_label_lean_pros_cons_and_sources(self) -> None:
        text = self.build()
        self.assertIn("# IPO research: Acme", text)
        self.assertIn("Not investment advice", text)
        self.assertIn("Report date: 2026-11-08 | Data status: UNVERIFIED", text)
        self.assertIn("**Leaning towards applying** (confidence: medium)", text)
        self.assertIn("Demand looks strong but valuation is rich.", text)
        self.assertIn("It cannot know your goals, finances or risk tolerance", text)
        self.assertIn("- Strong order book", text)
        self.assertIn("- Rich valuation", text)
        self.assertIn(f"| {NEWS} | 2 days ago (about 2026-11-06) | unverified |", text)
        self.assertIn("This does not make it correct.", text)

    def test_avoid_and_neutral_wording(self) -> None:
        self.assertIn("Leaning towards skipping", self.build(view=view(lean="avoid")))
        self.assertIn("Undecided", self.build(view=view(lean="neutral")))

    def test_without_sources_the_lean_is_neutral_and_the_reason_is_hidden(self) -> None:
        text = self.build(sources=[], view=view(lean="apply", confidence="high"))
        self.assertIn("Undecided", text)
        self.assertIn("(confidence: low)", text)
        self.assertNotIn("Demand looks strong", text)
        self.assertIn("No source URL could be confirmed", text)

    def test_untraced_numbers_are_called_out(self) -> None:
        text = self.build(untraced=["999"])
        self.assertIn("**Warning:** these numbers do not appear in any search snippet", text)
        self.assertIn("999", text)

    def test_missing_pros_and_cons_say_none_found(self) -> None:
        text = self.build(view=view(pros=[], cons=[]))
        self.assertEqual(text.count("- none found"), 2)

    def test_no_view_gives_a_note_and_status(self) -> None:
        text = self.build(view=None, sources=[], note="The IPO news search found nothing usable.")
        self.assertIn("Data status: no usable news found", text)
        self.assertIn("found nothing usable", text)
        self.assertIn("UNVERIFIED", text)


class StageTests(unittest.TestCase):
    def build(self, **changes):
        return build_ipo_report(
            "Acme", view(**changes), SOURCES, [], report_date="2026-11-08"
        )

    def test_listed_issue_says_applying_is_no_longer_possible_and_hides_the_lean(self) -> None:
        text = self.build(stage="listed", lean="apply", confidence="high")
        self.assertIn("## Where this IPO stands", text)
        self.assertIn("**Stage: listed.**", text)
        self.assertIn("applying is no longer possible", text)
        self.assertNotIn("Leaning towards", text)
        self.assertNotIn("confidence:", text)
        self.assertIn("- Strong order book", text)  # the news is still shown

    def test_closed_issue_points_to_the_buy_after_listing_question(self) -> None:
        text = self.build(stage="closed")
        self.assertIn("The bidding has closed", text)
        self.assertIn("buy after listing", text)

    def test_open_and_upcoming_and_unknown_keep_the_normal_lean(self) -> None:
        for stage in ("open", "upcoming", "unknown"):
            self.assertIn("Leaning towards applying", self.build(stage=stage), stage)

    def test_no_confirmed_source_still_wins_over_the_stage(self) -> None:
        lean, confidence, note = effective_lean(view(stage="listed"), [])
        self.assertEqual((lean, confidence), ("neutral", "low"))
        self.assertIn("No source URL could be confirmed", note)


class DateTests(unittest.TestCase):
    TODAY = date(2026, 11, 8)

    def test_relative_dates_get_an_absolute_date(self) -> None:
        self.assertEqual(absolute_date("2 days ago", self.TODAY), "2 days ago (about 2026-11-06)")
        self.assertEqual(absolute_date("1 week ago", self.TODAY), "1 week ago (about 2026-11-01)")
        self.assertEqual(absolute_date("2 weeks ago", self.TODAY), "2 weeks ago (about 2026-10-25)")

    def test_absolute_and_missing_dates_are_left_alone(self) -> None:
        self.assertEqual(absolute_date("19 Oct 2026", self.TODAY), "19 Oct 2026")
        self.assertEqual(absolute_date(None, self.TODAY), "Not stated")


class CrewTests(unittest.TestCase):
    def test_analyst_has_the_search_tool_and_checked_output(self) -> None:
        crew = IpoNewsCrew().crew()
        self.assertIs(crew.tasks[0].output_pydantic, IpoView)
        self.assertEqual([t.name for t in crew.agents[0].tools], ["Source search"])
        self.assertIn("{company}", crew.tasks[0].description)
        self.assertIn("{today}", crew.tasks[0].description)


class IpoFlowTests(unittest.TestCase):
    def run_flow(self, crew, client=None):
        identity = fake_crew(SimpleNamespace(pydantic=None))
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            os.chdir(tmp)
            try:
                with mock.patch.object(main, "IdentityCrew", identity), \
                     mock.patch.object(main, "IpoNewsCrew", crew), \
                     mock.patch.object(main, "get_search_client", return_value=client or client_with_news()), \
                     mock.patch.object(main, "reset_search_client"), \
                     mock.patch.object(main.time, "sleep"):
                    main.ResearchFlow().kickoff(
                        {"crewai_trigger_payload": {"company": "Acme IPO", "mode": "ipo"}}
                    )
                text = Path("output/report.md").read_text(encoding="utf-8")
            finally:
                os.chdir(previous)
        identity.assert_not_called()
        return text

    @staticmethod
    def output(v):
        return SimpleNamespace(tasks_output=[SimpleNamespace(pydantic=v)])

    def test_good_run_gives_lean_sources_with_dates_and_a_clean_number_check(self) -> None:
        text = self.run_flow(fake_crew(self.output(view())))
        self.assertIn("**Leaning towards applying** (confidence: medium)", text)
        self.assertIn(f"| {NEWS} | 2 days ago (about ", text)
        self.assertIn("every number in this text appears in a search snippet", text)

    def test_invented_number_and_invented_url_are_caught(self) -> None:
        crew = fake_crew(self.output(view(
            summary="The issue size is 7,777 crore.", source_urls=[NEWS, "https://made.up/x"],
        )))
        text = self.run_flow(crew)
        self.assertIn("**Warning:** these numbers do not appear", text)
        self.assertIn("7,777", text)
        self.assertNotIn("made.up", text)

    def test_all_urls_invented_forces_a_neutral_lean(self) -> None:
        text = self.run_flow(fake_crew(self.output(view(source_urls=["https://made.up/x"]))))
        self.assertIn("Undecided", text)
        self.assertIn("No source URL could be confirmed", text)

    def test_the_crew_is_given_todays_date(self) -> None:
        crew = fake_crew(self.output(view()))
        self.run_flow(crew)
        inputs = crew.return_value.crew.return_value.kickoff.call_args.kwargs["inputs"]
        self.assertEqual(inputs["today"], date.today().isoformat())
        self.assertEqual(inputs["company"], "Acme IPO")

    def test_empty_summary_gives_the_nothing_usable_note(self) -> None:
        text = self.run_flow(fake_crew(self.output(view(summary="  "))))
        self.assertIn("The IPO news search found nothing usable.", text)

    def test_crashing_crew_still_saves_a_report(self) -> None:
        text = self.run_flow(crashing_crew("Invalid API key"))
        self.assertIn("# IPO research: Acme IPO", text)
        self.assertIn("The IPO news research could not run. RuntimeError", text)


if __name__ == "__main__":
    unittest.main()
