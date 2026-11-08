"""Two-page spreads: two printed pages on one wide PDF page. Made-up pages only."""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("SERPER_API_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_generalised import BANNER_PAGE, NCI_PAGE  # noqa: E402

from stock_ipo_research_agent.report import figures_table  # noqa: E402
from stock_ipo_research_agent.tools.annual_report_reader import (  # noqa: E402
    SPREAD_BREAK,
    AnnualReportReader,
)
from stock_ipo_research_agent.tools.financial_facts import FinancialFacts  # noqa: E402
from stock_ipo_research_agent.tools.narrative_input import build_writer_input  # noqa: E402
from stock_ipo_research_agent.tools.statement_extractor import extract_pl_headlines  # noqa: E402
from stock_ipo_research_agent.tools.statement_locator import (  # noqa: E402
    CONSOLIDATED,
    PROFIT_AND_LOSS,
    STANDALONE,
    StatementLocation,
    get_statement,
    locate_statements,
)


class FakeHalf:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class FakePage:
    def __init__(self, width: float, height: float, left: str, right: str) -> None:
        self.width, self.height = width, height
        self.bbox = (0, 0, width, height)
        self._texts = (left, right)

    def crop(self, box):
        return FakeHalf(self._texts[0 if box[0] == 0 else 1])

    def extract_text(self) -> str:
        return " | ".join(self._texts)


class ReaderTests(unittest.TestCase):
    def test_wide_page_is_read_as_two_halves(self) -> None:
        page = FakePage(1188, 792, "left text", "right text")
        self.assertEqual(AnnualReportReader._page_text(page), f"left text{SPREAD_BREAK}right text")

    def test_normal_page_is_unchanged(self) -> None:
        page = FakePage(595, 842, "left", "right")
        self.assertEqual(AnnualReportReader._page_text(page), "left | right")


class SpreadLocateExtractTests(unittest.TestCase):
    def pages(self):
        return ["cover", "balance sheet text" + SPREAD_BREAK + BANNER_PAGE]

    def test_statement_on_the_right_half_is_located_with_its_pdf_page(self) -> None:
        found = locate_statements(self.pages())
        self.assertEqual(found, [StatementLocation(PROFIT_AND_LOSS, STANDALONE, (2,))])
        self.assertEqual(found[0].parts, ((2, 1),))

    def test_figures_cite_the_pdf_page_and_the_half(self) -> None:
        pages = self.pages()
        location = get_statement(locate_statements(pages), PROFIT_AND_LOSS, STANDALONE)
        figures = extract_pl_headlines(location, pages)
        self.assertEqual({f.pdf_page for f in figures}, {2})
        self.assertEqual({f.page_label for f in figures}, {"2 (right half)"})

    def test_normal_page_has_no_half_in_its_label(self) -> None:
        pages = [BANNER_PAGE]
        location = get_statement(locate_statements(pages), PROFIT_AND_LOSS, STANDALONE)
        figures = extract_pl_headlines(location, pages)
        self.assertEqual({f.page_label for f in figures}, {"1"})
        self.assertIsNone(figures[0].page_side)

    def test_statement_continues_from_a_right_half_to_the_next_left_half(self) -> None:
        second = "Consolidated Statement of Profit and Loss (contd.) (` in Crores) Earnings per share"
        pages = ["cover", "notes text" + SPREAD_BREAK + NCI_PAGE, second + SPREAD_BREAK + "other text"]
        found = locate_statements(pages)
        self.assertEqual(found, [StatementLocation(PROFIT_AND_LOSS, CONSOLIDATED, (2, 3))])
        self.assertEqual(found[0].parts, ((2, 1), (3, 0)))

    def test_left_and_right_halves_can_hold_different_statements(self) -> None:
        pages = [BANNER_PAGE.replace("Standalone", "Consolidated") + SPREAD_BREAK + BANNER_PAGE]
        bases = [(loc.basis, loc.parts) for loc in locate_statements(pages)]
        self.assertEqual(bases, [(CONSOLIDATED, ((1, 0),)), (STANDALONE, ((1, 1),))])

    def test_report_table_and_writer_input_show_the_half(self) -> None:
        pages = self.pages()
        location = get_statement(locate_statements(pages), PROFIT_AND_LOSS, STANDALONE)
        facts = FinancialFacts(
            source_url="https://example.com/ar.pdf", document_sha256="0" * 64, total_pages=2,
            identity_evidence=[], figures=extract_pl_headlines(location, pages), problems=[],
        )
        self.assertIn("| 2 (right half) |", figures_table(facts))
        self.assertIn("PDF page 2 (right half)", build_writer_input(facts))


if __name__ == "__main__":
    unittest.main()
