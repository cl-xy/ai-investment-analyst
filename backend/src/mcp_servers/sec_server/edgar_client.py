import logging
import os
import re
import threading
import time
from html import unescape

import httpx

log = logging.getLogger(__name__)

# SEC fair-access policy asks for a real contact in the User-Agent.
HEADERS = {
    "User-Agent": os.environ.get("SEC_USER_AGENT", "ai-investment-analyst xinyilu2000@gmail.com")
}
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
_load_lock = threading.Lock()


def _load_ticker_map() -> None:
    global _ticker_to_cik, _ticker_map_loaded, _last_load_attempt
    if _ticker_map_loaded:
        return
    with _load_lock:
        # Double-check after acquiring lock
        if _ticker_map_loaded:
            return
        if _last_load_attempt and (time.monotonic() - _last_load_attempt) < _RETRY_COOLDOWN_SECONDS:
            return
        try:
            r = _client.get(COMPANY_TICKERS_URL)
            r.raise_for_status()
            new_map: dict[str, str] = {}
            for entry in r.json().values():
                ticker = entry.get("ticker", "").upper()
                cik_raw = entry.get("cik_str")
                if not ticker or not cik_raw:
                    continue
                cik = str(cik_raw).zfill(10)
                new_map[ticker] = cik
            # Atomic swap: readers never see a partially built dict
            _ticker_to_cik = new_map
            _ticker_map_loaded = True
        except Exception as exc:
            log.warning(
                "Failed to load SEC ticker map: %s. Will retry after %ds.",
                exc,
                _RETRY_COOLDOWN_SECONDS,
            )
        finally:
            _last_load_attempt = time.monotonic()


def get_cik(ticker: str) -> str | None:
    _load_ticker_map()
    return _ticker_to_cik.get(ticker.upper())


def search_filings(ticker: str, form_type: str = "10-K", count: int = 3) -> list[dict]:
    if count <= 0:
        return []
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
        primary_docs = filings.get("primaryDocument", [])
        results = []
        for i, (form, date, acc) in enumerate(zip(forms, dates, accessions)):
            if form == form_type:
                acc_clean = acc.replace("-", "")
                results.append(
                    {
                        "form_type": form,
                        "filed_date": date,
                        "accession_number": acc,
                        "primary_document": primary_docs[i] if i < len(primary_docs) else "",
                        "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{acc}-index.htm",
                    }
                )
                if len(results) >= count:
                    break
        return results
    except Exception as exc:
        log.warning("Failed to search filings for %s: %s", ticker, exc)
        return []


# Exhibits (EX-19, EX-21, EX-23, EX-31, EX-32 ...) sort ahead of the main document
# on the filing index page, so they must never win the fallback pick.
_EXHIBIT_NAME_RE = re.compile(r"(ex[-_]?\d|exhibit|consent|subsidiar|certif)", re.IGNORECASE)
_BUSINESS_HEADING_RE = re.compile(r"item\s*1\.?\s*business", re.IGNORECASE)


def _html_to_text(html: str) -> str:
    # Inline XBRL filings start with a hidden <ix:header> block of facts and
    # contexts that would otherwise fill the excerpt with noise.
    html = re.sub(r"<ix:header>.*?</ix:header>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode entities (&#160; and friends) so the heading regex sees real spaces.
    return re.sub(r"\s+", " ", unescape(text)).strip()


_NEXT_ITEM_RE = re.compile(r"item\s*1a", re.IGNORECASE)


def _excerpt(text: str, max_chars: int) -> str:
    """Start at the body of Item 1 rather than the cover page and table of contents.

    A table of contents entry is followed almost immediately by "Item 1A", while
    the real heading is followed by pages of business description first.
    """
    for m in _BUSINESS_HEADING_RE.finditer(text):
        window = text[m.end() : m.end() + 800]
        if not _NEXT_ITEM_RE.search(window):
            return text[m.start() : m.start() + max_chars]
    return text[:max_chars]


def _pick_primary_document(index_html: str) -> str:
    links = re.findall(r'href="(/Archives/edgar/data/[^"]+\.htm)"', index_html, re.IGNORECASE)
    for link in links:
        if not _EXHIBIT_NAME_RE.search(link.rsplit("/", 1)[-1]):
            return link
    return ""


def get_filing_text_snippet(
    accession_number: str,
    cik: str,
    max_chars: int = 3000,
    primary_document: str = "",
) -> str:
    try:
        acc_clean = accession_number.replace("-", "")
        cik_int = int(cik)
        base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}"
        if primary_document:
            doc_url = f"{base}/{primary_document}"
        else:
            r = _client.get(f"{base}/{accession_number}-index.htm")
            r.raise_for_status()
            path = _pick_primary_document(r.text)
            if not path:
                return ""
            doc_url = "https://www.sec.gov" + path
        r2 = _client.get(doc_url, timeout=30)
        r2.raise_for_status()
        return _excerpt(_html_to_text(r2.text), max_chars)
    except Exception as exc:
        log.warning("Failed to get filing snippet for %s (CIK %s): %s", accession_number, cik, exc)
        return ""
