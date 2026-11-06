import json
import unittest
from pathlib import Path

from stock_ipo_research_agent.tools.statement_locator import (
    BALANCE_SHEET,
    CASH_FLOW,
    CONSOLIDATED,
    PROFIT_AND_LOSS,
    STANDALONE,
    StatementLocation,
    get_statement,
    locate_statements,
)

R = "\u20b9"  # rupee sign
CACHE = Path(__file__).resolve().parent.parent / "cache" / "tmpv_ar_2025_26.json"


class SyntheticTests(unittest.TestCase):
    def test_finds_statements_with_basis_and_repeated_headings(self) -> None:
        pages = [
            "cover",
            f"Consolidated Balance Sheet ({R} in crores) as at March 31",
            f"Consolidated Statement of Profit and Loss ({R} in crores) Revenue from operations Total income",
            f"Consolidated Statement of Profit and Loss ({R} in crores) Revenue from operations Total income",
            f"Balance Sheet ({R} in crores) as at March 31",
        ]
        self.assertEqual(
            locate_statements(pages),
            [
                StatementLocation(BALANCE_SHEET, CONSOLIDATED, (2,)),
                StatementLocation(PROFIT_AND_LOSS, CONSOLIDATED, (3, 4)),
                StatementLocation(BALANCE_SHEET, STANDALONE, (5,)),
            ],
        )

    def test_notes_and_subtable_pages_are_rejected(self) -> None:
        pages = [
            f"Notes forming part of consolidated financial statements balance sheet ({R} in crores)",
            f"b. Statement of Profit and Loss ({R} in crores) year ended",
            f"d) Re-presented Statement of Profit and Loss ({R} in crores)",
            f"Auditor report: the Balance Sheet ({R} in crores) is fine",
        ]
        self.assertEqual(locate_statements(pages), [])

    def test_title_without_unit_is_rejected(self) -> None:
        self.assertEqual(locate_statements(["Balance Sheet 331 Statement of Cash Flows 334"]), [])

    def test_untitled_continuation_page_joins_the_statement(self) -> None:
        pages = [
            f"Statement of Cash Flows ({R} in crores) year ended",
            f"({R} in crores) year ended particulars realisation of deposits",
            "459 tata motors passenger vehicles limited rotated text",
        ]
        self.assertEqual(
            locate_statements(pages), [StatementLocation(CASH_FLOW, STANDALONE, (1, 2))]
        )

    def test_continuation_is_bounded_and_must_be_contiguous(self) -> None:
        cont = f"({R} in crores) particulars"
        pages = [f"Balance Sheet ({R} in crores) as at", cont, cont, cont]
        self.assertEqual(
            locate_statements(pages, max_continuation=2)[0].pdf_pages, (1, 2, 3)
        )
        gap = [f"Balance Sheet ({R} in crores) as at", "unrelated page", cont]
        self.assertEqual(locate_statements(gap)[0].pdf_pages, (1,))

    def test_get_statement_handles_missing_and_ambiguous(self) -> None:
        a = StatementLocation(BALANCE_SHEET, CONSOLIDATED, (1,))
        b = StatementLocation(BALANCE_SHEET, CONSOLIDATED, (9,))
        self.assertIsNone(get_statement([a], CASH_FLOW, CONSOLIDATED))
        self.assertEqual(get_statement([a], BALANCE_SHEET, CONSOLIDATED), a)
        with self.assertRaises(ValueError):
            get_statement([a, b], BALANCE_SHEET, CONSOLIDATED)


@unittest.skipUnless(CACHE.exists(), "cached TMPV pages not present (cache/ is gitignored)")
class GoldenTmpvTests(unittest.TestCase):
    """Real page numbers verified from the probe output on the TMPV FY26 report."""

    def test_tmpv_statement_pages(self) -> None:
        pages = json.loads(CACHE.read_text(encoding="utf-8"))
        self.assertEqual(
            locate_statements(pages),
            [
                StatementLocation(BALANCE_SHEET, CONSOLIDATED, (331,)),
                StatementLocation(PROFIT_AND_LOSS, CONSOLIDATED, (332, 333)),
                StatementLocation(CASH_FLOW, CONSOLIDATED, (334, 335)),
                StatementLocation(BALANCE_SHEET, STANDALONE, (455,)),
                StatementLocation(PROFIT_AND_LOSS, STANDALONE, (456,)),
                StatementLocation(CASH_FLOW, STANDALONE, (457, 458)),
            ],
        )


if __name__ == "__main__":
    unittest.main()