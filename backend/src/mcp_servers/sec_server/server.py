from dotenv import load_dotenv

load_dotenv()

from fastmcp import FastMCP

from .edgar_client import get_cik, get_filing_text_snippet, search_filings

mcp = FastMCP("sec-server")


@mcp.tool()
def search_sec_filings(ticker: str, form_type: str = "10-K", count: int = 3) -> list[dict]:
    """
    Search for recent SEC filings for a company by ticker.
    form_type: '10-K' (annual), '10-Q' (quarterly), '8-K' (current events).
    Returns list of {form_type, filed_date, accession_number, url}.
    """
    return search_filings(ticker, form_type, count)


@mcp.tool()
def get_latest_filing_summary(ticker: str, form_type: str = "10-K") -> dict:
    """
    Fetch the latest SEC filing for a ticker and return a text excerpt for LLM analysis.
    Returns {ticker, form_type, filed_date, url, text_excerpt}.
    text_excerpt is the first ~3000 chars of the document after stripping HTML.
    """
    filings = search_filings(ticker, form_type, count=1)
    if not filings:
        return {"ticker": ticker.upper(), "form_type": form_type, "error": "No filings found"}
    latest = filings[0]
    cik = get_cik(ticker)
    if not cik:
        return {**latest, "ticker": ticker.upper(), "text_excerpt": ""}
    text = get_filing_text_snippet(latest["accession_number"], cik)
    return {
        "ticker": ticker.upper(),
        "form_type": form_type,
        "filed_date": latest["filed_date"],
        "url": latest["url"],
        "text_excerpt": text,
    }


if __name__ == "__main__":
    mcp.run()
