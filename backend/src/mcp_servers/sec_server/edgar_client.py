import logging
import re
import time

import httpx

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "mcp-investment-analyst contact@example.com"}
EDGAR_BASE = "https://efts.sec.gov"
SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Module-level client reuses TCP connections across calls (SEC rate limit: 10 req/s)
_client = httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True)

# Avoid hammering SEC on every call during an outage, while still recovering
# once it comes back, instead of permanently disabling lookups for the
# process lifetime after a single transient failure.
_RETRY_COOLDOWN_SECONDS = 300

_ticker_to_cik: dict[str, str] = {}
_ticker_map_loaded: bool = False
_last_load_attempt: float = 0.0


def _load_ticker_map() -> None:
    global _ticker_map_loaded, _last_load_attempt
    if _ticker_map_loaded:
        return
    if _last_load_attempt and (time.monotonic() - _last_load_attempt) < _RETRY_COOLDOWN_SECONDS:
        return
    _last_load_attempt = time.monotonic()
    try:
        r = _client.get(COMPANY_TICKERS_URL)
        r.raise_for_status()
        for entry in r.json().values():
            ticker = entry.get("ticker", "").upper()
            cik = str(entry.get("cik_str", "")).zfill(10)
            if ticker:
                _ticker_to_cik[ticker] = cik
        _ticker_map_loaded = True
    except Exception as exc:
        log.warning(
            "Failed to load SEC ticker map: %s. Will retry after %ds.",
            exc,
            _RETRY_COOLDOWN_SECONDS,
        )


def get_cik(ticker: str) -> str | None:
    _load_ticker_map()
    return _ticker_to_cik.get(ticker.upper())


def search_filings(ticker: str, form_type: str = "10-K", count: int = 3) -> list[dict]:
    cik = get_cik(ticker)
    if not cik:
        return []
    try:
        url = f"{SUBMISSIONS_BASE}/CIK{cik}.json"
        r = _client.get(url)
        r.raise_for_status()
        data = r.json()
        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accessions = filings.get("accessionNumber", [])
        results = []
        for form, date, acc in zip(forms, dates, accessions):
            if form == form_type:
                acc_clean = acc.replace("-", "")
                results.append(
                    {
                        "form_type": form,
                        "filed_date": date,
                        "accession_number": acc,
                        "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{acc}-index.htm",
                    }
                )
                if len(results) >= count:
                    break
        return results
    except Exception:
        return []


def get_filing_text_snippet(accession_number: str, cik: str, max_chars: int = 3000) -> str:
    acc_clean = accession_number.replace("-", "")
    cik_int = int(cik)
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{accession_number}-index.htm"
    try:
        r = _client.get(index_url)
        r.raise_for_status()
        # Extract the primary document link from the index page
        matches = re.findall(r'href="(/Archives/edgar/data/[^"]+\.htm)"', r.text, re.IGNORECASE)
        if not matches:
            return ""
        doc_url = "https://www.sec.gov" + matches[0]
        r2 = _client.get(doc_url, timeout=30)
        r2.raise_for_status()
        # Strip HTML tags for a rough text extraction
        text = re.sub(r"<[^>]+>", " ", r2.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception:
        return ""
