import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # to reuse the page fixtures

from test_statement_extractor import CONSOLIDATED_PAGE, STANDALONE_PAGE  # noqa: E402

from stock_ipo_research_agent.models import CompanyCandidate  # noqa: E402
from stock_ipo_research_agent.tools.annual_report_reader import (  # noqa: E402
    DocumentIdentityError,
    DocumentReaderError,
)
from stock_ipo_research_agent.tools.financial_facts import (  # noqa: E402
    extract_pl_facts,
    get_company,
    read_facts_for_agent,
    reset_company,
    set_company,
)
from stock_ipo_research_agent.tools.search import SearchClient  # noqa: E402

URL = "https://nsearchives.nseindia.com/annual_reports/AR.pdf"
COMPANY = CompanyCandidate(
    legal_name="Test Motors Limited", nse_symbol="TEST", isin="INE000A01010",
    business="Cars", source_url=URL,
)


class FakeLoader:
    """Stands in for the PDF reader: no download, no PDF."""

    def __init__(self, pages=None, error=None):
        self.pages = pages
        self.error = error
        self.calls = 0

    def load(self, source_url, company):
        self.calls += 1
        if self.error:
            raise self.error
        return self.pages, "a" * 64, ["Legal name: Test Motors Limited", "Identifier: INE000A01010"]


def client_that_saw(url=URL) -> SearchClient:
    session = mock.Mock()
    session.post.return_value.json.return_value = {
        "organic": [{"title": "Annual report", "link": url, "snippet": "x"}]
    }
    client = SearchClient(api_key="k", session=session)
    client.search("annual report")
    return client


def empty_client() -> SearchClient:
    return SearchClient(api_key="k", session=mock.Mock())


class ExtractFactsTests(unittest.TestCase):
    def test_both_bases_are_extracted_with_page_and_unit(self) -> None:
        loader = FakeLoader(["cover", CONSOLIDATED_PAGE, STANDALONE_PAGE])
        facts = extract_pl_facts(URL, COMPANY, loader=loader)
        self.assertEqual(facts.problems, [])
        self.assertEqual(len(facts.figures), 16)  # 4 rows x 2 years x 2 bases
        revenue = [
            f for f in facts.figures
            if f.key == "total_revenue_from_operations"
            and f.basis == "consolidated" and f.period == "March 31, 2026"
        ][0]
        self.assertEqual((revenue.value, revenue.unit, revenue.pdf_page), (Decimal(335582), "INR crore", 2))

    def test_a_missing_statement_is_a_problem_not_a_guess(self) -> None:
        facts = extract_pl_facts(URL, COMPANY, loader=FakeLoader(["cover", CONSOLIDATED_PAGE]))
        self.assertEqual(len(facts.figures), 8)
        self.assertEqual(len(facts.problems), 1)
        self.assertIn("standalone", facts.problems[0])

    def test_a_failed_cross_check_blocks_only_that_basis(self) -> None:
        bad = CONSOLIDATED_PAGE.replace("341,369 371,531", "341,000 371,531")
        facts = extract_pl_facts(URL, COMPANY, loader=FakeLoader(["cover", bad, STANDALONE_PAGE]))
        self.assertEqual({f.basis for f in facts.figures}, {"standalone"})
        self.assertIn("consolidated", facts.problems[0])


class AgentToolTests(unittest.TestCase):
    def test_unseen_url_is_refused_and_nothing_is_read(self) -> None:
        loader = FakeLoader(["cover", CONSOLIDATED_PAGE])
        text = read_facts_for_agent(URL, empty_client(), COMPANY, loader=loader)
        self.assertTrue(text.startswith("Refused"))
        self.assertEqual(loader.calls, 0)

    def test_no_confirmed_company_is_refused(self) -> None:
        loader = FakeLoader(["cover", CONSOLIDATED_PAGE])
        text = read_facts_for_agent(URL, client_that_saw(), None, loader=loader)
        self.assertTrue(text.startswith("Refused"))
        self.assertEqual(loader.calls, 0)

    def test_good_run_returns_figures_with_page_unit_and_source_line(self) -> None:
        loader = FakeLoader(["cover", CONSOLIDATED_PAGE, STANDALONE_PAGE])
        text = read_facts_for_agent(URL, client_that_saw(), COMPANY, loader=loader)
        self.assertIn("335,582 INR crore", text)
        self.assertIn("-1,377 INR crore", text)
        self.assertIn("PDF page 2", text)
        self.assertIn("(column marked *)", text)
        self.assertIn("line: I. Total revenue from operations 335,582 366,094", text)
        self.assertNotIn("Refused", text)

    def test_reader_and_identity_errors_become_a_clear_message(self) -> None:
        for error in (DocumentReaderError("not a PDF"), DocumentIdentityError("wrong company")):
            loader = FakeLoader(error=error)
            text = read_facts_for_agent(URL, client_that_saw(), COMPANY, loader=loader)
            self.assertTrue(text.startswith("Could not read the report"))
            self.assertIn("Do not guess", text)

    def test_problems_are_listed_for_the_agent(self) -> None:
        loader = FakeLoader(["cover", CONSOLIDATED_PAGE])
        text = read_facts_for_agent(URL, client_that_saw(), COMPANY, loader=loader)
        self.assertIn("Could not extract", text)
        self.assertIn("standalone", text)


class CompanyStateTests(unittest.TestCase):
    def test_set_get_reset(self) -> None:
        reset_company()
        self.assertIsNone(get_company())
        set_company(COMPANY)
        self.assertEqual(get_company(), COMPANY)
        reset_company()
        self.assertIsNone(get_company())


if __name__ == "__main__":
    unittest.main()