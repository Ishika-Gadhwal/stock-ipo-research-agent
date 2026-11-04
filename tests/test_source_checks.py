import unittest
from unittest import mock

from stock_ipo_research_agent.tools.search import SearchClient
from stock_ipo_research_agent.tools.source_checks import build_source_table

PAYLOAD = {
    "organic": [
        {
            "title": "Annual Report | FY26",
            "link": "https://nsearchives.nseindia.com/annual_reports/AR.pdf",
            "snippet": "x",
            "date": "15 Jun 2026",
        },
        {"title": "Fake NSE", "link": "https://evilnseindia.com/page", "snippet": "y"},
    ]
}


def seeded_client() -> SearchClient:
    session = mock.Mock()
    session.post.return_value.json.return_value = PAYLOAD
    client = SearchClient(api_key="k", session=session)
    client.search("anything")
    return client


class BuildSourceTableTests(unittest.TestCase):
    def test_title_date_and_type_come_from_the_search_result(self) -> None:
        table, rejected = build_source_table(
            ["https://nsearchives.nseindia.com/annual_reports/AR.pdf"], seeded_client()
        )
        self.assertEqual(rejected, [])
        self.assertIn("15 Jun 2026", table)
        self.assertIn("official", table)
        self.assertIn("Annual Report / FY26", table)  # the | in the title cannot break the table

    def test_url_never_returned_by_a_search_is_rejected(self) -> None:
        table, rejected = build_source_table(["https://invented.example/ar.pdf"], seeded_client())
        self.assertEqual(rejected, ["https://invented.example/ar.pdf"])
        self.assertEqual(table, "No verified sources found.")

    def test_lookalike_domain_is_unverified_not_official(self) -> None:
        table, _ = build_source_table(["https://evilnseindia.com/page"], seeded_client())
        self.assertIn("unverified", table)
        self.assertNotIn("official", table)

    def test_missing_date_is_shown_as_not_stated(self) -> None:
        table, _ = build_source_table(["https://evilnseindia.com/page"], seeded_client())
        self.assertIn("Not stated", table)

    def test_duplicates_appear_once_even_with_a_trailing_slash(self) -> None:
        urls = [
            "https://nsearchives.nseindia.com/annual_reports/AR.pdf",
            "https://nsearchives.nseindia.com/annual_reports/AR.pdf/",
        ]
        table, rejected = build_source_table(urls, seeded_client())
        self.assertEqual(table.count("nsearchives"), 1)
        self.assertEqual(rejected, [])

    def test_mixed_input_keeps_good_rows_and_lists_rejected(self) -> None:
        urls = ["https://nsearchives.nseindia.com/annual_reports/AR.pdf", "https://made-up.example/x"]
        table, rejected = build_source_table(urls, seeded_client())
        self.assertIn("nsearchives", table)
        self.assertEqual(rejected, ["https://made-up.example/x"])


if __name__ == "__main__":
    unittest.main()