import os
import unittest
from unittest import mock

import requests

from stock_ipo_research_agent.tools.search import (
    OFFICIAL,
    UNVERIFIED,
    SearchClient,
    SearchError,
    classify_source,
    format_results,
    get_search_client,
    normalise_url,
    reset_search_client,
)

PAYLOAD = {
    "organic": [
        {
            "title": "Tata Motors Passenger Vehicles Ltd - NSE",
            "link": "https://www.nseindia.com/get-quotes/equity?symbol=TMPV",
            "snippet": "Live quote.",
            "date": "2 days ago",
        },
        {"title": "No link here", "snippet": "dropped"},
        {"title": "Blog post", "link": "https://example.com/post/", "snippet": "opinion"},
    ]
}


def client_returning(payload=None, error=None):
    session = mock.Mock()
    if error:
        session.post.side_effect = error
    else:
        response = mock.Mock()
        response.json.return_value = payload
        session.post.return_value = response
    return SearchClient(api_key="test-key", session=session), session


class SearchTests(unittest.TestCase):
    def test_results_carry_url_date_and_code_assigned_source_type(self) -> None:
        client, _ = client_returning(PAYLOAD)
        results = client.search("tmpv")
        self.assertEqual(len(results), 2)  # the item without a link is dropped
        self.assertEqual(results[0].date, "2 days ago")
        self.assertEqual(results[0].source_type, OFFICIAL)
        self.assertIsNone(results[1].date)
        self.assertEqual(results[1].source_type, UNVERIFIED)

    def test_only_returned_urls_count_as_seen(self) -> None:
        client, _ = client_returning(PAYLOAD)
        client.search("tmpv")
        self.assertTrue(client.was_seen("https://example.com/post"))  # trailing slash ignored
        self.assertTrue(client.was_seen("HTTPS://EXAMPLE.COM/post#top"))  # host case, fragment
        self.assertFalse(client.was_seen("https://example.com/other"))
        self.assertFalse(client.was_seen("https://invented.example/annual-report.pdf"))

    def test_lookup_returns_the_real_result_for_a_seen_url(self) -> None:
        client, _ = client_returning(PAYLOAD)
        client.search("tmpv")
        found = client.lookup("https://www.nseindia.com/get-quotes/equity?symbol=TMPV")
        self.assertEqual(found.title, "Tata Motors Passenger Vehicles Ltd - NSE")
        self.assertEqual(found.date, "2 days ago")
        self.assertIsNone(client.lookup("https://invented.example/x"))

    def test_request_is_sent_with_key_and_limits(self) -> None:
        client, session = client_returning(PAYLOAD)
        client.search("  tmpv annual report  ")
        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["headers"]["X-API-KEY"], "test-key")
        self.assertEqual(kwargs["json"], {"q": "tmpv annual report", "num": 5, "gl": "in"})

    def test_empty_query_is_rejected_before_any_request(self) -> None:
        client, session = client_returning(PAYLOAD)
        with self.assertRaises(ValueError):
            client.search("   ")
        session.post.assert_not_called()

    def test_missing_api_key_is_a_clear_error(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SearchError):
                SearchClient(session=mock.Mock()).search("tmpv")

    def test_network_failure_becomes_search_error(self) -> None:
        client, _ = client_returning(error=requests.ConnectionError("down"))
        with self.assertRaises(SearchError):
            client.search("tmpv")

    def test_http_error_becomes_search_error(self) -> None:
        session = mock.Mock()
        session.post.return_value.raise_for_status.side_effect = requests.HTTPError("503")
        with self.assertRaises(SearchError):
            SearchClient(api_key="k", session=session).search("tmpv")

    def test_format_lists_urls_dates_and_source_type(self) -> None:
        client, _ = client_returning(PAYLOAD)
        text = format_results(client.search("tmpv"))
        self.assertIn("URL: https://www.nseindia.com/get-quotes/equity?symbol=TMPV", text)
        self.assertIn("Date: not stated", text)
        self.assertIn("Source type: official", text)
        self.assertEqual(format_results([]), "No results found.")


class ResetTests(unittest.TestCase):
    def test_reset_gives_a_fresh_empty_client(self) -> None:
        first = get_search_client()
        self.assertIs(first, get_search_client())  # shared within a run
        reset_search_client()
        self.assertIsNot(first, get_search_client())  # new run, new registry


class ClassifyTests(unittest.TestCase):
    def test_exchange_and_sebi_hosts_are_official(self) -> None:
        for url in (
            "https://www.nseindia.com/x",
            "https://nsearchives.nseindia.com/annual_reports/a.pdf",
            "https://www.bseindia.com/x",
            "https://www.sebi.gov.in/filings",
        ):
            self.assertEqual(classify_source(url), OFFICIAL, url)

    def test_lookalikes_and_garbage_are_unverified(self) -> None:
        for url in (
            "https://evilnseindia.com/x",
            "https://nseindia.com.evil.example/x",
            "https://example.com/nseindia.com",
            "not a url",
            "",
        ):
            self.assertEqual(classify_source(url), UNVERIFIED, url)

    def test_normalise_url(self) -> None:
        self.assertEqual(normalise_url("HTTPS://Example.com/a/#x"), "https://example.com/a")


if __name__ == "__main__":
    unittest.main()