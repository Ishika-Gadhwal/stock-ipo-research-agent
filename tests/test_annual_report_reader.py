import unittest

from stock_ipo_research_agent.models import CompanyCandidate
from stock_ipo_research_agent.tools.annual_report_reader import (
    AnnualReportReader,
    DocumentIdentityError,
)


class AnnualReportReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = AnnualReportReader(identity_page_limit=2)
        self.company = CompanyCandidate(
            legal_name="Example Industries Limited",
            nse_symbol="EXAMPLE",
            bse_code="123456",
            isin="INE000A01000",
            business="Example business",
            source_url="https://example.test/company",
        )

    def test_identity_requires_legal_name_and_identifier(self) -> None:
        evidence = self.reader._validate_identity(
            ["Example Industries Limited\nNSE: EXAMPLE", "Annual report"], self.company
        )
        self.assertEqual(evidence, ["Legal name: Example Industries Limited", "Identifier: EXAMPLE"])

    def test_identity_rejects_wrong_entity_even_when_an_identifier_appears(self) -> None:
        with self.assertRaises(DocumentIdentityError):
            self.reader._validate_identity(["Different Company\nNSE: EXAMPLE"], self.company)

    def test_legal_name_is_sufficient_when_the_report_omits_an_identifier(self) -> None:
        lenient = AnnualReportReader(identity_page_limit=2, require_identifier=False)
        evidence = lenient._validate_identity(["Example Industries Limited annual report"], self.company)
        self.assertEqual(evidence, [
            "Legal name: Example Industries Limited",
            "No exact exchange identifier found in document",
        ])

    def test_strict_mode_rejects_a_legal_name_without_an_identifier(self) -> None:
        with self.assertRaises(DocumentIdentityError):  # strict is the default
            self.reader._validate_identity(["Example Industries Limited annual report"], self.company)



    def test_relevant_pages_are_bounded_and_include_context(self) -> None:
        pages = ["cover", "before", "Consolidated Revenue from operations", "after", "another hit: revenue"]
        excerpts = self.reader._find_excerpts(
            pages, ["revenue from operations"], context_pages=1, max_excerpt_pages=3
        )
        self.assertEqual([excerpt.pdf_page for excerpt in excerpts], [2, 3, 4])
        self.assertEqual(excerpts[1].matched_terms, ["revenue from operations"])

    def test_empty_terms_are_rejected_before_download(self) -> None:
        with self.assertRaises(ValueError):
            self.reader.read("https://example.test/report.pdf", self.company, ["  "])


    def test_formerly_name_is_not_the_current_legal_name(self) -> None:
        old_name = self.company.model_copy(update={"legal_name": "Old Name Limited"})
        pages = ["Example Industries Limited\n(formerly Old Name Limited)\nNSE: EXAMPLE"]
        with self.assertRaises(DocumentIdentityError):
            self.reader._validate_identity(pages, old_name)

    def test_identifier_is_found_beyond_the_front_pages(self) -> None:
        pages = ["Example Industries Limited", "x", "x", "NSE \u2013 Stock Code EXAMPLE"]
        evidence = self.reader._validate_identity(pages, self.company)
        self.assertIn("Identifier: EXAMPLE", evidence)

    def test_heading_pages_outrank_pages_that_only_mention_the_term(self) -> None:
        pages = ["x" * 500 + " Auditor says: Consolidated Balance Sheet is fine",
         "x" * 500,
         "Consolidated Balance Sheet\n(\u20b9 in crores)", "x"]
        excerpts = self.reader._find_excerpts(
            pages, ["consolidated balance sheet"], context_pages=0, max_excerpt_pages=1,
            heading_only=True,
        )
        self.assertEqual([e.pdf_page for e in excerpts], [3]) 


if __name__ == "__main__":
    unittest.main()
