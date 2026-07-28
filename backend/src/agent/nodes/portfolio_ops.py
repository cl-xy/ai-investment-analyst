import json
import re

from langchain_core.messages import AIMessage

from ..state import InvestmentAnalystState


def _parse_tool_result(result) -> dict | list | str:
    """
    LangChain MCP tools return results as a list of content blocks:
    [{'type': 'text', 'text': '<json>', 'id': '...'}]
    Extract and parse the first text block.
    """
    if isinstance(result, (dict, list)) and not (
        isinstance(result, list) and result and isinstance(result[0], dict) and "type" in result[0]
    ):
        return result
    if isinstance(result, list):
        for block in result:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block["text"]
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, ValueError):
                    return text
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (json.JSONDecodeError, ValueError):
            return result
    return result


async def portfolio_ops_node(state: InvestmentAnalystState, *, mcp_tools: dict) -> dict:
    intent = state.get("intent")
    last_message = state["messages"][-1]
    raw_content = last_message.content if hasattr(last_message, "content") else str(last_message)
    user_text = raw_content if isinstance(raw_content, str) else str(raw_content)

    get_portfolio = mcp_tools.get("get_portfolio")
    add_position = mcp_tools.get("add_position")
    remove_position = mcp_tools.get("remove_position")

    if intent == "list_portfolio":
        if get_portfolio:
            raw = await get_portfolio.ainvoke({})
            positions = _parse_tool_result(raw)
            positions = positions if isinstance(positions, list) else []
            if not positions:
                reply = "Your portfolio is currently empty."
            else:
                lines = ["**Your Portfolio:**\n"]
                lines.append("| Ticker | Shares | Cost Basis | Sector |")
                lines.append("|--------|--------|------------|--------|")
                for p in positions:
                    lines.append(
                        f"| {p['ticker']} | {p['shares']} | ${p['cost_basis']:.2f} | {p.get('sector', 'Unknown')} |"
                    )
                reply = "\n".join(lines)
        else:
            reply = "Portfolio server not available."
        return {"messages": [AIMessage(content=reply)]}

    if intent == "add_position" and add_position:
        tickers = state.get("tickers_to_analyze", [])
        ticker = tickers[0] if tickers else None
        if not ticker:
            return {"messages": [AIMessage(content="Please specify a ticker symbol.")]}
        shares_match = re.search(r"(\d+(?:\.\d+)?)\s*shares?", user_text, re.IGNORECASE)
        cost_match = re.search(
            r"\$?(\d+(?:\.\d+)?)\s*(?:per share|cost|@)", user_text, re.IGNORECASE
        )
        sector_match = re.search(r"sector[:\s]+([A-Za-z &]+?)(?:\)|,|$)", user_text, re.IGNORECASE)
        shares = float(shares_match.group(1)) if shares_match else 1.0
        cost_basis = float(cost_match.group(1)) if cost_match else 0.0
        sector = sector_match.group(1).strip() if sector_match else "Unknown"
        raw = await add_position.ainvoke(
            {"ticker": ticker, "shares": shares, "cost_basis": cost_basis, "sector": sector}
        )
        parsed = _parse_tool_result(raw)
        msg = parsed.get("message", str(parsed)) if isinstance(parsed, dict) else str(parsed)
        return {"messages": [AIMessage(content=msg)]}

    if intent == "remove_position" and remove_position:
        tickers = state.get("tickers_to_analyze", [])
        ticker = tickers[0] if tickers else None
        if not ticker:
            return {"messages": [AIMessage(content="Please specify a ticker symbol to remove.")]}
        raw = await remove_position.ainvoke({"ticker": ticker})
        parsed = _parse_tool_result(raw)
        msg = parsed.get("message", str(parsed)) if isinstance(parsed, dict) else str(parsed)
        return {"messages": [AIMessage(content=msg)]}

    return {"messages": [AIMessage(content="Portfolio operation not recognized.")]}
