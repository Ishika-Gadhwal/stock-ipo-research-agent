"""Layout styles seen in other companies' annual reports. The pages below are made up
to copy each style (page banner, stray rupee sign, million unit, date styles, two
tables on one line). No real report text is stored here."""

import unittest
from decimal import Decimal

from stock_ipo_research_agent.tools.statement_extractor import (
    ExtractionError,
    extract_pl_headlines,
    normalise_label,
    parse_row,
)
from stock_ipo_research_agent.tools.statement_locator import (
    CONSOLIDATED,
    PROFIT_AND_LOSS,
    STANDALONE,
    StatementLocation,
    locate_statements,
)

BANNER_PAGE = """Acme Ltd Annual Report 2025-26 120
Standalone Statement of Profit and Loss
for the year ended 31st March, 2026
(` in Crores)
Particulars Note 31st March, 2026 31st March, 2025
I Revenue From Operations 22A, 22B 1,000.50 900.25
II Other Income 23 50.00 40.00
III Total Income (I+II) 1,050.50 940.25
IX Profit for the year (VII-VIII) 200.00 150.00
"""

MILLION_PAGE = """Standalone Statement of Profit and Loss
for the year ended March 31, 2026
\u20b9 in Million
March 31, 2026 March 31, 2025
(I) Revenue from operations 29 2,000.4 1,900.0
(II) Other income 30 100.3 90.0
(III) Total income (I + II) 2,100.7 1,990.0
(IX) Profit / (loss) for the year (VII - VIII) 300.2 280.0
"""

OVER_YEARS_PAGE = """Standalone Statement of Profit and Loss
(In ` crore, except per share data)
Particulars Note Year ended March 31,
2026 2025
Revenue from operations 2.18 1,48,819 1,36,592
Other income, net 2.19 6,491 4,782
Total income 1,55,310 1,41,374
Profit for the year 29,211 25,568
"""

FISCAL_LABEL_PAGE = """Standalone Statement of Profit and Loss for the year ended March 31, 2026
v crore
Particulars Note 2025-26 2024-25
Revenue from operations 31 153680.17 142509.01
Other income (net) 32 7358.45 5669.21
Total Income 161038.62 148178.22
Net Profit after tax 6287.13 10870.72
Profit for the year 6200.00 10800.00
"""

TWO_TABLES_PAGE = """Financial Statements
Standalone Statement of Profit and Loss
for the year ended 31st March, 2026
(All amounts in ` crores, unless otherwise stated) (All amounts in ` crores, unless otherwise stated)
Year ended Year ended
Particulars Note Particulars Note
31st March, 2026 31st March, 2025 31st March, 2026 31st March, 2025
Revenue from operations 25 6,000 5,000 Remeasurements of the net defined benefit plans 39C 8 (22)
Other income 26 100 90 Tax on above 9A (2) 5
TOTAL INCOME 6,100 5,090 Items that will be reclassified to profit or loss
PROFIT FOR THE YEAR FROM CONTINUING OPERATIONS (A) 1,000 900
PROFIT FOR THE YEAR (C=A+B) 1,500 800 Chartered Accountants Managing Director
"""

NCI_PAGE = """Consolidated Statement of Profit and Loss
\u20b9 in Million
March 31, 2026 March 31, 2025
(I) Revenue from operations 500 400
(II) Other income 20 10
(III) Total income (I + II) 520 410
(IX) Profit for the year before share of profit of associates (VII-VIII) 90 70
(XII) Profit for the year before non-controlling interests (IX+X+XI) 85 66
(XIV) Profit for the year attributable to owners of the parent (XII-XIII) 80 60
"""


def extract(text: str):
    pages = [text]
    return extract_pl_headlines(StatementLocation(PROFIT_AND_LOSS, STANDALONE, (1,)), pages)


def values(figures):
    return {(f.key, f.period): f.value for f in figures}


class LocatorStyleTests(unittest.TestCase):
    def test_page_banner_standalone_prefix_and_stray_rupee_sign(self) -> None:
        found = locate_statements([BANNER_PAGE])
        self.assertEqual(found, [StatementLocation(PROFIT_AND_LOSS, STANDALONE, (1,))])

    def test_million_and_fiscal_label_pages_are_found(self) -> None:
        self.assertEqual(len(locate_statements([MILLION_PAGE, "cover", FISCAL_LABEL_PAGE])), 2)

    def test_consolidated_prefix_still_gives_consolidated(self) -> None:
        self.assertEqual(locate_statements([NCI_PAGE])[0].basis, CONSOLIDATED)

    def test_continuation_page_with_the_same_heading_joins_even_without_income_rows(self) -> None:
        second = "Consolidated Statement of Profit and Loss (contd.) (` in Crores) Earnings per share"
        found = locate_statements([NCI_PAGE, second, "cover"])
        self.assertEqual(found, [StatementLocation(PROFIT_AND_LOSS, CONSOLIDATED, (1, 2))])

    def test_profit_page_without_income_rows_is_rejected(self) -> None:
        page = "Standalone Statement of Profit and Loss (` in Crores) contents page 12"
        self.assertEqual(locate_statements([page]), [])


class ExtractionStyleTests(unittest.TestCase):
    def test_banner_page_gives_all_eight_figures(self) -> None:
        figures = extract(BANNER_PAGE)
        self.assertEqual(len(figures), 8)
        got = values(figures)
        self.assertEqual(got[("total_revenue_from_operations", "March 31, 2026")], Decimal("1000.50"))
        self.assertEqual(got[("profit_for_the_year", "March 31, 2025")], Decimal("150.00"))
        self.assertEqual(figures[0].unit, "INR crore")

    def test_million_unit_is_kept_and_not_called_crore(self) -> None:
        figures = extract(MILLION_PAGE)
        self.assertEqual({f.unit for f in figures}, {"INR million"})

    def test_year_ended_march_31_printed_over_the_years(self) -> None:
        figures = extract(OVER_YEARS_PAGE)
        got = values(figures)
        self.assertEqual(got[("total_revenue_from_operations", "March 31, 2026")], Decimal(148819))
        self.assertEqual(got[("total_income", "March 31, 2025")], Decimal(141374))

    def test_fiscal_year_labels_and_strong_profit_row_wins(self) -> None:
        got = values(extract(FISCAL_LABEL_PAGE))
        self.assertEqual(got[("profit_for_the_year", "March 31, 2026")], Decimal("6200.00"))
        self.assertIn(("total_income", "March 31, 2025"), got)

    def test_two_tables_on_one_line_read_only_the_left_one(self) -> None:
        figures = extract(TWO_TABLES_PAGE)
        got = values(figures)
        self.assertEqual(got[("total_revenue_from_operations", "March 31, 2026")], Decimal(6000))
        self.assertEqual(got[("total_income", "March 31, 2025")], Decimal(5090))
        # continuing operations beats the plain "profit for the year" row
        self.assertEqual(got[("profit_from_continuing_operations", "March 31, 2026")], Decimal(1000))
        self.assertNotIn(("profit_for_the_year", "March 31, 2026"), got)

    def test_profit_before_non_controlling_interests_is_the_headline(self) -> None:
        got = values(extract(NCI_PAGE))
        self.assertEqual(got[("profit_for_the_year", "March 31, 2026")], Decimal(85))

    def test_foreign_currency_header_is_refused(self) -> None:
        page = BANNER_PAGE.replace("(` in Crores)", "(US$ in million)")
        with self.assertRaises(ExtractionError):
            extract(page)

    def test_unknown_year_style_is_refused(self) -> None:
        page = BANNER_PAGE.replace("31st March, 2026 31st March, 2025", "FY current FY previous")
        with self.assertRaises(ExtractionError):
            extract(page)


class RowHelperTests(unittest.TestCase):
    def test_numerals_are_removed_only_when_they_are_whole_tokens(self) -> None:
        self.assertEqual(normalise_label("(III) Total income (I + II)"), "total income (i + ii)")
        self.assertEqual(normalise_label("IX. Profit for the year"), "profit for the year")
        self.assertEqual(normalise_label("Interest income"), "interest income")
        self.assertEqual(normalise_label("Liabilities"), "liabilities")

    def test_indian_digit_grouping_and_decimal_note(self) -> None:
        row = parse_row("Revenue from operations 2.18 1,48,819 1,36,592")
        self.assertEqual((row.current, row.previous), (Decimal(148819), Decimal(136592)))

    def test_a_row_that_ends_in_two_figures_is_unchanged(self) -> None:
        row = parse_row("II. Other income 34 5,787 5,437")
        self.assertEqual((row.label, row.note), ("II. Other income", "34"))


if __name__ == "__main__":
    unittest.main()
