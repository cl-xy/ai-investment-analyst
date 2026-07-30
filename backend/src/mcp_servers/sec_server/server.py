import logging

from dotenv import load_dotenv

load_dotenv()

from fastmcp import FastMCP

from src.validation import validate_ticker_or_none as _validate_ticker

from .edgar_client import get_cik, get_filing_text_snippet, search_filings

log = logging.getLogger(__name__)

mcp = FastMCP("sec-server")

_VALID_FORM_TYPES = {"10-K", "10-Q", "8-K", "S-1", "DEF 14A"}
_MAX_COUNT = 20


@mcp.tool()
def search_sec_filings(ticker: str, form_type: str = "10-K", count: int = 3) -> list[dict]:
    """
    Search for recent SEC filings for a company by ticker.
    form_type: '10-K' (annual), '10-Q' (quarterly), '8-K' (current events).
    Returns list of {form_type, filed_date, accession_number, url}.
    """
    normalized = _validate_ticker(ticker)
    if not normalized:
        return [{"error": "Invalid ticker format", "data_gaps": ["ticker_validation"]}]

    form_type = form_type.strip().upper() if isinstance(form_type, str) else "10-K"
    if form_type not in _VALID_FORM_TYPES:
        return [{"error": f"Unsupported form type: {form_type}", "data_gaps": ["form_type_validation"]}]

    count = max(1, min(int(count), _MAX_COUNT))

    try:
        results = search_filings(normalized, form_type, count)
        if not isinstance(results, list):
            return []
        return results
    except Exception as exc:
        log.warning("search_sec_filings failed for %s: %s", normalized, exc)
        return [{"error": f"Filing search failed: {exc}", "data_gaps": ["sec_search_failure"]}]


@mcp.tool()
def get_latest_filing_summary(ticker: str, form_type: str = "10-K") -> dict:
    """
    Fetch the latest SEC filing for a ticker and return a text excerpt for LLM analysis.
    Returns {ticker, form_type, filed_date, url, text_excerpt, data_gaps}.
    text_excerpt is the first ~3000 chars of the document after stripping HTML.
    """
    normalized = _validate_ticker(ticker)
    if not normalized:
        return {
            "ticker": ticker if isinstance(ticker, str) else "",
            "form_type": form_type,
            "error": "Invalid ticker format",
            "data_gaps": ["ticker_validation"],
        }

    form_type = form_type.strip().upper() if isinstance(form_type, str) else "10-K"
    if form_type not in _VALID_FORM_TYPES:
        return {
            "ticker": normalized,
            "form_type": form_type,
            "error": f"Unsupported form type: {form_type}",
            "data_gaps": ["form_type_validation"],
        }

    data_gaps: list[str] = []

    try:
        filings = search_filings(normalized, form_type, count=1)
    except Exception as exc:
        log.warning("search_filings failed for %s: %s", normalized, exc)
        return {
            "ticker": normalized,
            "form_type": form_type,
            "error": f"Filing search failed: {exc}",
            "data_gaps": ["sec_search_failure"],
        }

    if not filings or not isinstance(filings, list):
        return {
            "ticker": normalized,
            "form_type": form_type,
            "error": "No filings found",
            "data_gaps": ["no_filings"],
        }

    latest = filings[0]
    if not isinstance(latest, dict):
        return {
            "ticker": normalized,
            "form_type": form_type,
            "error": "Malformed filing data",
            "data_gaps": ["malformed_filing_response"],
        }

    filed_date = latest.get("filed_date", "")
    url = latest.get("url", "")
    accession_number = latest.get("accession_number", "")

    text_excerpt = ""
    if accession_number:
        try:
            cik = get_cik(normalized)
            if cik:
                text_excerpt = get_filing_text_snippet(accession_number, cik)
                if not isinstance(text_excerpt, str):
                    text_excerpt = ""
                    data_gaps.append("text_extraction_invalid_type")
            else:
                data_gaps.append("cik_lookup_failed")
        except Exception as exc:
            log.warning("Filing text extraction failed for %s: %s", normalized, exc)
            data_gaps.append("text_extraction_failed")
    else:
        data_gaps.append("missing_accession_number")

    result = {
        "ticker": normalized,
        "form_type": form_type,
        "filed_date": filed_date,
        "url": url,
        "text_excerpt": text_excerpt,
    }
    if data_gaps:
        result["data_gaps"] = data_gaps
    return result


if __name__ == "__main__":
    mcp.run()
