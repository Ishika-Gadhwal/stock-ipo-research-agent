import json
import unittest
from decimal import Decimal
from pathlib import Path

from stock_ipo_research_agent.tools.statement_extractor import (
    ExtractionError,
    extract_pl_headlines,
    parse_number,
    parse_row,
    read_header,
)
from stock_ipo_research_agent.tools.statement_locator import (
    CONSOLIDATED,
    PROFIT_AND_LOSS,
    STANDALONE,
    StatementLocation,
    get_statement,
    locate_statements,
)

R = "\u20b9"
CACHE = Path(__file__).resolve().parent.parent / "cache" / "tmpv_ar_2025_26.json"

# Short excerpts of the REAL lines printed by scripts/page_probe.py (TMPV FY26).
CONSOLIDATED_PAGE = f"""Consolidated Statement of Profit and Loss
({R} in crores)
Year ended Year ended
Particulars Notes
March 31, 2026 March 31, 2025*
Revenue from operations 33
(a) Revenue 333,383 363,486
(b) Other operating revenues 2,199 2,608
I. Total revenue from operations 335,582 366,094
II. Other income 34 5,787 5,437
III. Total income (I+II) 341,369 371,531
IV. Expenses:
(c) Changes in inventories of finished goods, work-in-progress and products for sale 1,661 2,060
(i) Product development/engineering expenses 37(ii)(b) 11,863 10,318
IX. Profit/(loss) before tax from continuing operations (VII-VIII) (1,623) 28,454
Tax expense/ (credit) of continuing operations 21 (246) 9,060
XI. Profit/(loss) after tax for the year from continuing operations (IX-X) (1,377) 19,394
XIII. Exceptional gain on disposal of discontinued operations 50 82,616 -
XV. Profit for the year after exceptional gain on disposal and tax from discontinued operations
(XII+XIII-XIV) 84,022 8,755
XVII. Profit for the year (XI+XV) 82,645 28,149"""

STANDALONE_PAGE = f"""Statement of Profit and Loss
({R} in crores)
Notes Year ended Year ended
Particulars
March 31, 2026 March 31, 2025*
Revenue from operations
(a) Revenue 57,409 49,211
I. Total revenue from operations 31 57,859 49,358
II. Other income 32 5,867 2,331
III. Total income (I+II) 63,726 51,689
(c) Changes in inventories of finished goods, work-in-progress and products for sale 6 3,645
IX. Profit for the year from continuing operations (VII-VIII) 3,839 1,538
X. Profit for the year before exceptional gain and tax from discontinued operations (refer note 50) 1,624 5,628
XV. Profit for the year (IX+XIII) 87,569 5,874"""


def figures_by_key(figures):
    return {(f.key, f.period): f for f in figures}


class ParseNumberTests(unittest.TestCase):
    def test_numbers(self) -> None:
        self.assertEqual(parse_number("335,582"), Decimal(335582))
        self.assertEqual(parse_number("(1,377)"), Decimal(-1377))
        self.assertEqual(parse_number("(4.43)"), Decimal("-4.43"))
        self.assertEqual(parse_number("-"), Decimal(0))

    def test_non_numbers(self) -> None:
        for token in ("37(ii)(b)", "(IX-X)", "(a)", "March", "(1,377", "1,377)"):
            self.assertIsNone(parse_number(token), token)


class ParseRowTests(unittest.TestCase):
    def test_plain_row(self) -> None:
        row = parse_row("I. Total revenue from operations 335,582 366,094")
        self.assertEqual((row.label, row.note), ("I. Total revenue from operations", None))
        self.assertEqual((row.current, row.previous), (Decimal(335582), Decimal(366094)))

    def test_note_is_separated_from_the_figures(self) -> None:
        row = parse_row("II. Other income 34 5,787 5,437")
        self.assertEqual((row.label, row.note), ("II. Other income", "34"))
        self.assertEqual((row.current, row.previous), (Decimal(5787), Decimal(5437)))

    def test_compound_note(self) -> None:
        row = parse_row("(i) Product development/engineering expenses 37(ii)(b) 11,863 10,318")
        self.assertEqual(row.note, "37(ii)(b)")
        self.assertEqual(row.current, Decimal(11863))

    def test_tiny_value_is_a_value_not_a_note(self) -> None:
        row = parse_row("(c) Changes in inventories of finished goods and products for sale 6 3,645")
        self.assertIsNone(row.note)
        self.assertEqual((row.current, row.previous), (Decimal(6), Decimal(3645)))

    def test_nil_and_negative(self) -> None:
        nil = parse_row("XIII. Exceptional gain on disposal of discontinued operations 50 82,616 -")
        self.assertEqual((nil.note, nil.current, nil.previous), ("50", Decimal(82616), Decimal(0)))
        neg = parse_row("(f) Compulsorily convertible preference shares gain (178) (84)")
        self.assertEqual((neg.current, neg.previous), (Decimal(-178), Decimal(-84)))

    def test_dash_inside_a_label_is_not_a_value(self) -> None:
        row = parse_row("VI. Exceptional items - loss (net) 38 523 30")
        self.assertEqual((row.label, row.note), ("VI. Exceptional items - loss (net)", "38"))
        self.assertEqual((row.current, row.previous), (Decimal(523), Decimal(30)))

    def test_non_rows(self) -> None:
        self.assertIsNone(parse_row("Revenue from operations 33"))  # header with a note
        self.assertIsNone(parse_row("IV. Expenses:"))
        self.assertIsNone(parse_row("XV. Profit for the year after exceptional gain on disposal"))

    def test_wrapped_row_parses_only_its_last_line(self) -> None:
        row = parse_row("(XII+XIII-XIV) 84,022 8,755")
        self.assertEqual(row.label, "(XII+XIII-XIV)")  # partial label: do not match on it


class HeaderTests(unittest.TestCase):
    def test_unit_and_columns_in_printed_order(self) -> None:
        unit, columns = read_header(CONSOLIDATED_PAGE)
        self.assertEqual(unit, "INR crore")
        self.assertEqual(columns, [("March 31, 2026", False), ("March 31, 2025", True)])

    def test_missing_unit_is_an_error(self) -> None:
        with self.assertRaises(ExtractionError):
            read_header("Statement of Profit and Loss\nMarch 31, 2026 March 31, 2025*")


class ExtractTests(unittest.TestCase):
    def test_consolidated_headlines(self) -> None:
        loc = StatementLocation(PROFIT_AND_LOSS, CONSOLIDATED, (1,))
        got = figures_by_key(extract_pl_headlines(loc, [CONSOLIDATED_PAGE]))
        self.assertEqual(len(got), 8)
        rev = got[("total_revenue_from_operations", "March 31, 2026")]
        self.assertEqual(rev.value, Decimal(335582))
        self.assertEqual((rev.unit, rev.basis, rev.pdf_page), ("INR crore", CONSOLIDATED, 1))
        self.assertFalse(rev.starred)
        self.assertIn("335,582", rev.source_line)
        self.assertTrue(got[("total_revenue_from_operations", "March 31, 2025")].starred)
        self.assertEqual(
            got[("profit_from_continuing_operations", "March 31, 2026")].value, Decimal(-1377)
        )
        self.assertEqual(
            got[("profit_from_continuing_operations", "March 31, 2025")].value, Decimal(19394)
        )

    def test_standalone_headlines_use_different_wording(self) -> None:
        loc = StatementLocation(PROFIT_AND_LOSS, STANDALONE, (1,))
        got = figures_by_key(extract_pl_headlines(loc, [STANDALONE_PAGE]))
        self.assertEqual(got[("total_revenue_from_operations", "March 31, 2026")].value, Decimal(57859))
        self.assertEqual(got[("profit_from_continuing_operations", "March 31, 2026")].value, Decimal(3839))
        self.assertEqual(got[("profit_from_continuing_operations", "March 31, 2025")].value, Decimal(1538))

    def test_cross_check_failure_blocks_the_result(self) -> None:
        bad = CONSOLIDATED_PAGE.replace("341,369 371,531", "341,000 371,531")
        loc = StatementLocation(PROFIT_AND_LOSS, CONSOLIDATED, (1,))
        with self.assertRaises(ExtractionError):
            extract_pl_headlines(loc, [bad])

    def test_missing_row_is_an_error(self) -> None:
        bad = CONSOLIDATED_PAGE.replace("II. Other income 34 5,787 5,437\n", "")
        loc = StatementLocation(PROFIT_AND_LOSS, CONSOLIDATED, (1,))
        with self.assertRaises(ExtractionError):
            extract_pl_headlines(loc, [bad])

    def test_duplicate_row_is_an_error(self) -> None:
        extra = CONSOLIDATED_PAGE + "\nI. Total revenue from operations 1 2"
        loc = StatementLocation(PROFIT_AND_LOSS, CONSOLIDATED, (1,))
        with self.assertRaises(ExtractionError):
            extract_pl_headlines(loc, [extra])

    def test_wrong_statement_type_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            extract_pl_headlines(StatementLocation("balance_sheet", CONSOLIDATED, (1,)), ["x"])


@unittest.skipUnless(CACHE.exists(), "cached TMPV pages not present (cache/ is gitignored)")
class GoldenTmpvTests(unittest.TestCase):
    def test_tmpv_headline_figures(self) -> None:
        pages = json.loads(CACHE.read_text(encoding="utf-8"))
        locations = locate_statements(pages)
        expect = {
            CONSOLIDATED: {"rev": (335582, 366094), "profit": (-1377, 19394)},
            STANDALONE: {"rev": (57859, 49358), "profit": (3839, 1538)},
        }
        for basis, want in expect.items():
            loc = get_statement(locations, PROFIT_AND_LOSS, basis)
            got = figures_by_key(extract_pl_headlines(loc, pages))
            for key, short in (("total_revenue_from_operations", "rev"),
                               ("profit_from_continuing_operations", "profit")):
                self.assertEqual(got[(key, "March 31, 2026")].value, Decimal(want[short][0]), (basis, key))
                self.assertEqual(got[(key, "March 31, 2025")].value, Decimal(want[short][1]), (basis, key))


if __name__ == "__main__":
    unittest.main()