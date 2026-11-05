"""The router picks the path in code. No LLM, no network."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # reuse the other tests' fixtures
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

from test_financial_facts import COMPANY, URL, client_that_saw  # noqa: E402
from test_flow import content_output, fake_crew, fake_extract, writer_output  # noqa: E402

from stock_ipo_research_agent import main  # noqa: E402
from stock_ipo_research_agent.models import IdentityResult  # noqa: E402


class NormaliseModeTests(unittest.TestCase):
    def test_default_is_stock(self) -> None:
        self.assertEqual(main.normalise_mode(None), "stock")
        self.assertEqual(main.normalise_mode(""), "stock")

    def test_accepts_either_mode_in_any_case(self) -> None:
        self.assertEqual(main.normalise_mode(" IPO "), "ipo")
        self.assertEqual(main.normalise_mode("Stock"), "stock")

    def test_unknown_mode_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            main.normalise_mode("bond")


class RouterFlowTests(unittest.TestCase):
    def run_flow(self, payload):
        identity_crew = fake_crew(SimpleNamespace(pydantic=IdentityResult(candidates=[COMPANY])))
        content_crew = fake_crew(content_output([URL], URL))
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            os.chdir(tmp)
            try:
                with mock.patch.object(main, "IdentityCrew", identity_crew), \
                     mock.patch.object(main, "ContentCrew", content_crew), \
                     mock.patch.object(main, "NarrativeCrew", fake_crew(writer_output("Ok."))), \
                     mock.patch.object(main, "get_search_client", return_value=client_that_saw()), \
                     mock.patch.object(main, "reset_search_client"), \
                     mock.patch.object(main, "extract_pl_facts", side_effect=fake_extract), \
                     mock.patch("builtins.input", return_value="1"):
                    main.ResearchFlow().kickoff({"crewai_trigger_payload": payload})
                text = Path("output/report.md").read_text(encoding="utf-8")
            finally:
                os.chdir(previous)
        return text, identity_crew

    def test_ipo_mode_saves_a_stub_and_never_starts_the_stock_path(self) -> None:
        text, identity_crew = self.run_flow({"company": "Some IPO Ltd", "mode": "ipo"})
        self.assertIn("# IPO research: Some IPO Ltd", text)
        self.assertIn("The IPO path is not built yet", text)
        self.assertIn("Not investment advice", text)
        identity_crew.assert_not_called()

    def test_stock_mode_in_the_payload_runs_the_stock_path(self) -> None:
        text, identity_crew = self.run_flow({"company": "Tata Motors", "mode": "stock"})
        self.assertIn("# Research notes: Test Motors Limited", text)
        identity_crew.assert_called()

    def test_payload_without_mode_defaults_to_stock(self) -> None:
        text, _ = self.run_flow({"company": "Tata Motors"})
        self.assertIn("# Research notes: Test Motors Limited", text)


if __name__ == "__main__":
    unittest.main()