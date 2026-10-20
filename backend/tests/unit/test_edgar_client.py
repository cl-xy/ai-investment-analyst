"""Unit tests for the SEC EDGAR client: ticker map retry/cooldown, document selection, excerpts."""

from unittest.mock import MagicMock, patch

import pytest

from src.mcp_servers.sec_server import edgar_client


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _reset_module_state():
    """The ticker map is process-global state; reset it around every test."""
    edgar_client._ticker_to_cik.clear()
    edgar_client._ticker_map_loaded = False
    edgar_client._last_load_attempt = 0.0
    yield
    edgar_client._ticker_to_cik.clear()
    edgar_client._ticker_map_loaded = False
    edgar_client._last_load_attempt = 0.0


def test_load_ticker_map_success_populates_map(monkeypatch):
    monkeypatch.setattr(
        edgar_client._client,
        "get",
        lambda *a, **k: _FakeResponse({"0": {"ticker": "nvda", "cik_str": 1045810}}),
    )

    assert edgar_client.get_cik("NVDA") == "0001045810"
    assert edgar_client._ticker_map_loaded is True


def test_failure_does_not_permanently_disable_lookups(monkeypatch):
    calls = {"count": 0}

    def _failing_get(*a, **k):
        calls["count"] += 1
        raise ConnectionError("SEC unreachable")

    monkeypatch.setattr(edgar_client._client, "get", _failing_get)

    assert edgar_client.get_cik("NVDA") is None
    assert edgar_client._ticker_map_loaded is False
    assert calls["count"] == 1


def test_retry_is_skipped_within_cooldown_window(monkeypatch):
    calls = {"count": 0}

    def _failing_get(*a, **k):
        calls["count"] += 1
        raise ConnectionError("SEC unreachable")

    monkeypatch.setattr(edgar_client._client, "get", _failing_get)

    clock = {"t": 1000.0}
    monkeypatch.setattr(edgar_client.time, "monotonic", lambda: clock["t"])

    edgar_client.get_cik("NVDA")
    assert calls["count"] == 1

    # A second call shortly after the failure should NOT retry the network call.
    clock["t"] += 10
    edgar_client.get_cik("NVDA")
    assert calls["count"] == 1


def test_retry_succeeds_after_cooldown_elapses(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(edgar_client.time, "monotonic", lambda: clock["t"])

    calls = {"count": 0}

    def _get(*a, **k):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ConnectionError("SEC unreachable")
        return _FakeResponse({"0": {"ticker": "nvda", "cik_str": 1045810}})

    monkeypatch.setattr(edgar_client._client, "get", _get)

    assert edgar_client.get_cik("NVDA") is None
    assert calls["count"] == 1

    # Advance past the cooldown window — the next call should retry and succeed.
    clock["t"] += edgar_client._RETRY_COOLDOWN_SECONDS + 1
    assert edgar_client.get_cik("NVDA") == "0001045810"
    assert calls["count"] == 2
    assert edgar_client._ticker_map_loaded is True


# --- filing document selection and excerpt extraction ---

INDEX_HTML = """
<a href="/Archives/edgar/data/1045810/000104581026000021/nvda-2026xex191.htm">EX-19.1</a>
<a href="/Archives/edgar/data/1045810/000104581026000021/subsidiariesofregistrantfy.htm">EX-21</a>
<a href="/Archives/edgar/data/1045810/000104581026000021/a2026auditorconsentletter.htm">EX-23</a>
<a href="/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm">10-K</a>
"""


def test_exhibits_are_skipped_when_picking_the_main_document():
    path = edgar_client._pick_primary_document(INDEX_HTML)
    assert path.endswith("nvda-20260125.htm")


def test_no_main_document_returns_empty():
    html = '<a href="/Archives/edgar/data/1/2/ex31.htm">x</a>'
    assert edgar_client._pick_primary_document(html) == ""


def test_inline_xbrl_header_and_entities_are_stripped():
    html = (
        "<html><ix:header><ix:hidden>dei:Junk 12345</ix:hidden></ix:header>"
        "<body><p>Item&#160;1.&#160;Business</p><p>We make chips.</p></body></html>"
    )
    text = edgar_client._html_to_text(html)
    assert "Junk" not in text
    assert text == "Item 1. Business We make chips."


def test_excerpt_skips_the_table_of_contents():
    toc = "Item 1. Business 1 Item 1A. Risk Factors 5 Item 2. Properties 17 "
    body = "Item 1. Business " + "We design accelerated computing platforms. " * 30
    text = "FORM 10-K cover page " + toc + body
    out = edgar_client._excerpt(text, 200)
    assert out.startswith("Item 1. Business We design")
    assert "Risk Factors" not in out


def test_excerpt_falls_back_to_start_without_a_business_heading():
    assert edgar_client._excerpt("plain text only", 5) == "plain"


def test_primary_document_from_metadata_is_fetched_directly():
    html = "<p>Item 1. Business " + "x " * 500 + "</p>"
    resp = MagicMock(text=html)
    resp.raise_for_status.return_value = None
    with patch.object(edgar_client._client, "get", return_value=resp) as get:
        out = edgar_client.get_filing_text_snippet(
            "0001045810-26-000021", "0001045810", primary_document="nvda-20260125.htm"
        )

    assert out.startswith("Item 1. Business")
    # One request for the document itself, no index page lookup.
    assert get.call_count == 1
    assert get.call_args[0][0].endswith("/000104581026000021/nvda-20260125.htm")


def test_search_filings_returns_primary_document():
    payload = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-K"],
                "filingDate": ["2026-03-01", "2026-02-25"],
                "accessionNumber": ["0001-26-000001", "0001045810-26-000021"],
                "primaryDocument": ["a.htm", "nvda-20260125.htm"],
            }
        }
    }
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    with (
        patch.object(edgar_client, "get_cik", return_value="0001045810"),
        patch.object(edgar_client._client, "get", return_value=resp),
    ):
        results = edgar_client.search_filings("NVDA", "10-K", count=1)

    assert results[0]["primary_document"] == "nvda-20260125.htm"
    assert results[0]["accession_number"] == "0001045810-26-000021"
