import json
import logging
import re

from langchain_core.messages import AIMessage

from ..state import InvestmentAnalystState

logger = logging.getLogger(__name__)


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
                text = block.get("text")
                if not isinstance(text, str):
                    continue
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
    messages = state.get("messages") or []
    if not messages:
        return {"messages": [AIMessage(content="No message context available.")]}
    last_message = messages[-1]
    raw_content = last_message.content if hasattr(last_message, "content") else str(last_message)
    # Normalize list content blocks (multimodal format) to plain text
    if isinstance(raw_content, list):
        raw_content = " ".join(
            block.get("text", "") for block in raw_content if isinstance(block, dict)
        )
    user_text = raw_content if isinstance(raw_content, str) else str(raw_content)

    get_portfolio = mcp_tools.get("get_portfolio")
    add_position = mcp_tools.get("add_position")
    remove_position = mcp_tools.get("remove_position")

    if intent == "list_portfolio":
        if get_portfolio:
            try:
                raw = await get_portfolio.ainvoke({})
            except Exception as e:
                logger.warning("get_portfolio tool failed: %s", e)
                return {
                    "messages": [AIMessage(content="Failed to retrieve portfolio.")],
                    "data_gaps": ["portfolio: tool call failed"],
                }
            positions = _parse_tool_result(raw)
            positions = positions if isinstance(positions, list) else []
            if not positions:
                reply = "Your portfolio is currently empty."
            else:
                lines = ["**Your Portfolio:**\n"]
                lines.append("| Ticker | Shares | Cost Basis | Sector |")
                lines.append("|--------|--------|------------|--------|")
                for p in positions:
                    if not isinstance(p, dict):
                        continue
                    ticker = p.get("ticker", "N/A")
                    shares = p.get("shares", 0)
                    cost_basis = p.get("cost_basis", 0.0)
                    sector = p.get("sector", "Unknown")
                    try:
                        cost_str = f"${float(cost_basis):.2f}"
                    except (TypeError, ValueError):
                        cost_str = "$0.00"
                    lines.append(f"| {ticker} | {shares} | {cost_str} | {sector} |")
                reply = "\n".join(lines)
        else:
            reply = "Portfolio server not available."
        return {"messages": [AIMessage(content=reply)]}

    if intent == "add_position":
        if not add_position:
            return {"messages": [AIMessage(content="Portfolio server not available.")]}
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
        try:
            raw = await add_position.ainvoke(
                {"ticker": ticker, "shares": shares, "cost_basis": cost_basis, "sector": sector}
            )
        except Exception as e:
            logger.warning("add_position tool failed: %s", e)
            return {
                "messages": [AIMessage(content="Failed to add position.")],
                "data_gaps": ["portfolio: add_position tool call failed"],
            }
        parsed = _parse_tool_result(raw)
        msg = parsed.get("message", str(parsed)) if isinstance(parsed, dict) else str(parsed)
        return {"messages": [AIMessage(content=msg)]}

    if intent == "remove_position":
        if not remove_position:
            return {"messages": [AIMessage(content="Portfolio server not available.")]}
        tickers = state.get("tickers_to_analyze", [])
        ticker = tickers[0] if tickers else None
        if not ticker:
            return {"messages": [AIMessage(content="Please specify a ticker symbol to remove.")]}
        try:
            raw = await remove_position.ainvoke({"ticker": ticker})
        except Exception as e:
            logger.warning("remove_position tool failed: %s", e)
            return {
                "messages": [AIMessage(content="Failed to remove position.")],
                "data_gaps": ["portfolio: remove_position tool call failed"],
            }
        parsed = _parse_tool_result(raw)
        msg = parsed.get("message", str(parsed)) if isinstance(parsed, dict) else str(parsed)
        return {"messages": [AIMessage(content=msg)]}

    return {"messages": [AIMessage(content="Portfolio operation not recognized.")]}
