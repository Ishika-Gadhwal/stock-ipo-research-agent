"""Retry of temporary model errors, and the report's status line and sources note."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("SERPER_API_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_report import report  # noqa: E402

from stock_ipo_research_agent import main  # noqa: E402
from stock_ipo_research_agent.report import empty_facts  # noqa: E402

BUSY = "503 UNAVAILABLE. This model is currently experiencing high demand."


def crew_with(*outcomes):
    holder = mock.Mock()
    holder.return_value.crew.return_value.kickoff.side_effect = list(outcomes)
    return holder


def kickoffs(holder):
    return holder.return_value.crew.return_value.kickoff.call_count


class TransientTests(unittest.TestCase):
    def test_busy_model_rate_limit_and_timeout_are_temporary(self) -> None:
        for message in (BUSY, "429 RESOURCE_EXHAUSTED", "Request timed out", "Service Unavailable"):
            self.assertTrue(main._is_transient(RuntimeError(message)), message)

    def test_a_real_error_is_not_temporary(self) -> None:
        for message in ("Invalid API key", "Pydantic validation error", "KeyError: 'urls'"):
            self.assertFalse(main._is_transient(RuntimeError(message)), message)


class RetryTests(unittest.TestCase):
    def test_retries_a_busy_model_and_waits_between_attempts(self) -> None:
        crew = crew_with(RuntimeError(BUSY), RuntimeError(BUSY), "done")
        with mock.patch.object(main.time, "sleep") as sleep:
            self.assertEqual(main._run_with_retry(crew, {}), "done")
        self.assertEqual(kickoffs(crew), 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [5, 20])

    def test_a_real_error_raises_at_once_without_waiting(self) -> None:
        crew = crew_with(RuntimeError("Pydantic validation error"))
        with mock.patch.object(main.time, "sleep") as sleep, self.assertRaises(RuntimeError):
            main._run_with_retry(crew, {})
        self.assertEqual(kickoffs(crew), 1)
        sleep.assert_not_called()

    def test_gives_up_after_three_attempts(self) -> None:
        crew = crew_with(RuntimeError(BUSY), RuntimeError(BUSY), RuntimeError(BUSY))
        with mock.patch.object(main.time, "sleep"), self.assertRaises(RuntimeError):
            main._run_with_retry(crew, {})
        self.assertEqual(kickoffs(crew), 3)

    def test_summary_helper_retries_then_succeeds(self) -> None:
        crew = crew_with(RuntimeError(BUSY), "ok")
        with mock.patch.object(main.time, "sleep"):
            self.assertEqual(main._kickoff(crew, {}), ("ok", None))

    def test_summary_helper_returns_the_error_text_when_retries_run_out(self) -> None:
        crew = crew_with(RuntimeError(BUSY), RuntimeError(BUSY), RuntimeError(BUSY))
        with mock.patch.object(main.time, "sleep"):
            output, error = main._kickoff(crew, {})
        self.assertIsNone(output)
        self.assertIn("RuntimeError", error)


class PolishTests(unittest.TestCase):
    def test_status_line_for_verified_figures(self) -> None:
        text = report(report_date="2026-11-08")
        self.assertIn(
            "Report date: 2026-11-08 | Data status: verified figures extracted from the annual report",
            text,
        )

    def test_status_line_mentions_statements_that_could_not_be_read(self) -> None:
        facts = report.__globals__["FACTS"].model_copy(update={"problems": ["standalone: x"]})
        self.assertIn("(some statements could not be read)", report(facts=facts))

    def test_status_line_when_only_the_web_summary_exists(self) -> None:
        text = report(facts=empty_facts(), summary=None, web_summary="x", web_sources=[])
        self.assertIn("Data status: no verified figures; an UNVERIFIED web summary is included", text)

    def test_status_line_when_nothing_was_found(self) -> None:
        text = report(facts=empty_facts(), summary=None)
        self.assertIn("Data status: no figures found", text)

    def test_date_defaults_to_today(self) -> None:
        from datetime import date

        self.assertIn(f"Report date: {date.today().isoformat()}", report())

    def test_sources_note_explains_what_official_means(self) -> None:
        text = report()
        self.assertIn('"official" means the link is on an exchange or SEBI website', text)
        self.assertIn("does not prove the document belongs to this company", text)


if __name__ == "__main__":
    unittest.main()
