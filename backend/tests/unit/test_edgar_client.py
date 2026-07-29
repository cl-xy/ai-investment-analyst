"""Unit tests for the SEC EDGAR ticker map loader's retry/cooldown behavior."""

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
        edgar_client.httpx,
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

    monkeypatch.setattr(edgar_client.httpx, "get", _failing_get)

    assert edgar_client.get_cik("NVDA") is None
    assert edgar_client._ticker_map_loaded is False
    assert calls["count"] == 1


def test_retry_is_skipped_within_cooldown_window(monkeypatch):
    calls = {"count": 0}

    def _failing_get(*a, **k):
        calls["count"] += 1
        raise ConnectionError("SEC unreachable")

    monkeypatch.setattr(edgar_client.httpx, "get", _failing_get)

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

    monkeypatch.setattr(edgar_client.httpx, "get", _get)

    assert edgar_client.get_cik("NVDA") is None
    assert calls["count"] == 1

    # Advance past the cooldown window — the next call should retry and succeed.
    clock["t"] += edgar_client._RETRY_COOLDOWN_SECONDS + 1
    assert edgar_client.get_cik("NVDA") == "0001045810"
    assert calls["count"] == 2
    assert edgar_client._ticker_map_loaded is True
