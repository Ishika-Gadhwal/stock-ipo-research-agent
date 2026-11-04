import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # reuse the other tests' fixtures

from test_financial_facts import COMPANY, URL, FakeLoader  # noqa: E402
from test_statement_extractor import CONSOLIDATED_PAGE, STANDALONE_PAGE  # noqa: E402

from stock_ipo_research_agent.tools.financial_facts import extract_pl_facts  # noqa: E402
from stock_ipo_research_agent.tools.numbers_check import find_unverified_numbers  # noqa: E402

FACTS = extract_pl_facts(
    URL, COMPANY, loader=FakeLoader(["cover", CONSOLIDATED_PAGE, STANDALONE_PAGE])
)
# The fake pages put the consolidated P&L on PDF page 2 and the standalone on page 3.


class NumbersCheckTests(unittest.TestCase):
    def test_extracted_figures_and_their_pages_are_accepted(self) -> None:
        text = (
            "Consolidated revenue was \u20b9335,582 crore (PDF page 2), down from 366,094. "
            "Profit from continuing operations was a loss of (1,377), or -1,377 crore. "
            "Standalone revenue was 57,859 crore on page 3."
        )
        self.assertEqual(find_unverified_numbers(text, FACTS), [])

    def test_an_invented_number_is_flagged(self) -> None:
        text = "Revenue was 335,582 crore and the order book is 400,000 crore."
        self.assertEqual(find_unverified_numbers(text, FACTS), ["400,000"])

    def test_a_number_the_llm_computed_is_flagged(self) -> None:
        text = "Revenue fell by 8.3% and total income fell 29,000 crore."
        self.assertEqual(find_unverified_numbers(text, FACTS), ["8.3", "29,000"])

    def test_years_fiscal_year_labels_and_dates_are_ignored(self) -> None:
        text = "In FY26, for the year ended March 31, 2026 versus 2025 and FY2025-26, in Q3."
        self.assertEqual(find_unverified_numbers(text, FACTS), [])

    def test_a_wrong_page_number_is_flagged(self) -> None:
        self.assertEqual(find_unverified_numbers("See page 999.", FACTS), ["999"])

    def test_a_repeated_bad_number_is_listed_once(self) -> None:
        text = "It was 111,111 crore. Again, 111,111 crore."
        self.assertEqual(find_unverified_numbers(text, FACTS), ["111,111"])

    def test_punctuation_after_a_number_does_not_hide_it(self) -> None:
        text = "Revenue was 335,582, which is high. Debt was 777,000."
        self.assertEqual(find_unverified_numbers(text, FACTS), ["777,000"])

    def test_text_without_numbers_passes(self) -> None:
        self.assertEqual(find_unverified_numbers("No figures here.", FACTS), [])


if __name__ == "__main__":
    unittest.main()