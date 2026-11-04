import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # reuse the other tests' fixtures

from stock_ipo_research_agent.models import CompanyCandidate  # noqa: E402
from stock_ipo_research_agent.tools.annual_report_reader import (  # noqa: E402
    DocumentIdentityError,
    DocumentReaderError,
)
from stock_ipo_research_agent.tools.facts_selection import (  # noqa: E402
    annual_report_candidates,
    find_facts,
)
from stock_ipo_research_agent.tools.financial_facts import FinancialFacts  # noqa: E402
from stock_ipo_research_agent.tools.search import SearchClient  # noqa: E402

NSE = "https://nsearchives.nseindia.com/annual_reports/AR_29395_TMPV_2025_2026_A_1.pdf"
BSE = "https://www.bseindia.com/xml-data/corpfiling/AttachHis/abc.pdf"
SITE = "https://www.tatamotors.com/wp-content/uploads/2024/05/iar.pdf"
COMPANY = CompanyCandidate(
    legal_name="Tata Motors Passenger Vehicles Limited", nse_symbol="TMPV",
    business="Cars", source_url=NSE,
)
PAYLOAD = {
    "organic": [
        {"title": "Annual Reports", "link": "https://www.tatamotors.com/annual-reports/"},  # not a PDF
        {"title": "80TH INTEGRATED ANNUAL REPORT 2024-25", "link": SITE},
        {"title": "Integrated Annual Report for the Financial Year 2025-26", "link": BSE},
        {"title": "Integrated Annual Report for the Financial Year 2025-26", "link": NSE},
        {"title": "Annual report", "link": "http://example.com/annual-report.pdf"},  # not https
        {"title": "Quarterly results", "link": "https://example.com/results.pdf"},  # not an annual report
    ]
}


def client_with(payload) -> SearchClient:
    session = mock.Mock()
    session.post.return_value.json.return_value = payload
    client = SearchClient(api_key="k", session=session)
    client.search("annual report")
    return client


def facts_for(url: str) -> FinancialFacts:
    return FinancialFacts(
        source_url=url, document_sha256="a" * 64, total_pages=1,
        identity_evidence=[], figures=[], problems=[],
    )


class FakeExtract:
    """Records calls. URLs in `errors` raise the given error; the rest succeed."""

    def __init__(self, errors=None):
        self.errors = errors or {}
        self.calls = []

    def __call__(self, url, company):
        self.calls.append(url)
        if url in self.errors:
            raise self.errors[url]
        return facts_for(url)


class CandidateTests(unittest.TestCase):
    def test_ranking_prefers_nse_file_with_the_symbol_then_other_official_hosts(self) -> None:
        self.assertEqual(annual_report_candidates(client_with(PAYLOAD), COMPANY), [NSE, BSE, SITE])

    def test_non_pdf_http_and_non_annual_report_results_are_excluded(self) -> None:
        candidates = annual_report_candidates(client_with(PAYLOAD), COMPANY, limit=10)
        self.assertEqual(len(candidates), 3)
        self.assertNotIn("http://example.com/annual-report.pdf", candidates)
        self.assertNotIn("https://example.com/results.pdf", candidates)

    def test_limit_is_respected(self) -> None:
        self.assertEqual(annual_report_candidates(client_with(PAYLOAD), COMPANY, limit=1), [NSE])

    def test_nothing_that_no_search_returned_is_ever_a_candidate(self) -> None:
        empty = SearchClient(api_key="k", session=mock.Mock())
        self.assertEqual(annual_report_candidates(empty, COMPANY), [])


class FindFactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = client_with(PAYLOAD)

    def test_the_analysts_url_is_used_when_it_works(self) -> None:
        extract = FakeExtract()
        facts, notes = find_facts(self.client, COMPANY, BSE, extract=extract)
        self.assertEqual(facts.source_url, BSE)
        self.assertEqual((notes, extract.calls), ([], [BSE]))

    def test_no_analyst_url_falls_back_to_the_best_candidate(self) -> None:
        extract = FakeExtract()
        facts, notes = find_facts(self.client, COMPANY, None, extract=extract)
        self.assertEqual(facts.source_url, NSE)
        self.assertIn("did not select", notes[0])
        self.assertIn("Fell back", notes[-1])

    def test_an_unseen_analyst_url_is_never_read(self) -> None:
        extract = FakeExtract()
        made_up = "https://made-up.example/ar.pdf"
        facts, notes = find_facts(self.client, COMPANY, made_up, extract=extract)
        self.assertNotIn(made_up, extract.calls)
        self.assertIn("not returned by any search", notes[0])
        self.assertEqual(facts.source_url, NSE)

    def test_a_failing_analyst_url_falls_back_without_retrying_it(self) -> None:
        extract = FakeExtract({SITE: DocumentReaderError("not a PDF")})
        facts, notes = find_facts(self.client, COMPANY, SITE, extract=extract)
        self.assertEqual(extract.calls, [SITE, NSE])
        self.assertIn("Could not read", notes[0])
        self.assertEqual(facts.source_url, NSE)

    def test_a_rejected_candidate_is_noted_and_the_next_one_is_tried(self) -> None:
        extract = FakeExtract({NSE: DocumentIdentityError("wrong company")})
        facts, notes = find_facts(self.client, COMPANY, None, extract=extract)
        self.assertEqual(facts.source_url, BSE)
        self.assertTrue(any("Candidate rejected" in n and NSE in n for n in notes))

    def test_when_every_candidate_fails_there_are_no_facts_and_a_full_trail(self) -> None:
        errors = {u: DocumentIdentityError("wrong company") for u in (NSE, BSE, SITE)}
        extract = FakeExtract(errors)
        facts, notes = find_facts(self.client, COMPANY, None, extract=extract)
        self.assertIsNone(facts)
        self.assertEqual(len(extract.calls), 3)
        self.assertEqual(sum("Candidate rejected" in n for n in notes), 3)

    def test_no_annual_report_pdf_in_the_search_results(self) -> None:
        client = client_with({"organic": [{"title": "Investor relations", "link": "https://x.example/ir"}]})
        facts, notes = find_facts(client, COMPANY, None, extract=FakeExtract())
        self.assertIsNone(facts)
        self.assertEqual(len(notes), 1)


if __name__ == "__main__":
    unittest.main()
