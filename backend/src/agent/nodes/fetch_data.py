import asyncio
import json

from ..state import InvestmentAnalystState


def _unwrap(result) -> dict | list:
    """Unwrap LangChain MCP content-block format: [{'type':'text','text':'<json>'}]."""
    if isinstance(result, list) and result and isinstance(result[0], dict) and "type" in result[0]:
        for block in result:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, ValueError):
                    return block["text"]
        return {}
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (json.JSONDecodeError, ValueError):
            return result
    return result


async def _call_tool(tools: dict, name: str, **kwargs) -> dict | list:
    tool = tools.get(name)
    if tool is None:
        return {}
    try:
        raw = await tool.ainvoke(kwargs)
        return _unwrap(raw)
    except Exception as e:
        return {"error": str(e)}


async def fetch_data_node(state: InvestmentAnalystState, *, mcp_tools: dict) -> dict:
    tickers = state.get("tickers_to_analyze", [])
    if not tickers:
        return {}

    async def fetch_one(ticker: str):
        news, prices, fundamentals, filing, indicators = await asyncio.gather(
            _call_tool(mcp_tools, "get_ticker_news", ticker=ticker, days_back=7, max_articles=10),
            _call_tool(mcp_tools, "get_quote", ticker=ticker),
            _call_tool(mcp_tools, "get_fundamentals", ticker=ticker),
            _call_tool(mcp_tools, "get_latest_filing_summary", ticker=ticker, form_type="10-K"),
            _call_tool(mcp_tools, "get_technical_indicators", ticker=ticker),
        )
        return ticker, news, prices, fundamentals, filing, indicators

    results = await asyncio.gather(*[fetch_one(t) for t in tickers])

    raw_news = {}
    raw_prices = {}
    raw_filings = {}

    for ticker, news, prices, fundamentals, filing, indicators in results:
        raw_news[ticker] = news if isinstance(news, list) else []
        raw_prices[ticker] = {
            "quote": prices if isinstance(prices, dict) else {},
            "fundamentals": fundamentals if isinstance(fundamentals, dict) else {},
            "indicators": indicators if isinstance(indicators, dict) else {},
        }
        raw_filings[ticker] = filing.get("text_excerpt", "") if isinstance(filing, dict) else ""

    return {"raw_news": raw_news, "raw_prices": raw_prices, "raw_filings": raw_filings}
