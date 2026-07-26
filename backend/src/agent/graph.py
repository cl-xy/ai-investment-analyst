"""
Main LangGraph agent graph.

Usage (async context with MCP client active):

    async with create_mcp_client() as client:
        tools = {t.name: t for t in await client.get_tools()}
        graph = build_graph(tools)
        checkpointer = AsyncSqliteSaver.from_conn_string("data/checkpointer.db")
        compiled = graph.compile(checkpointer=checkpointer)
        result = await compiled.ainvoke(
            {"messages": [HumanMessage("Analyze NVDA")]},
            config={"configurable": {"thread_id": "my-session"}},
        )
"""

from functools import partial
from typing import Literal

from langgraph.graph import END, START, StateGraph

from .nodes.analyze_ticker import analyze_ticker_node
from .nodes.chat import chat_node
from .nodes.fetch_data import fetch_data_node
from .nodes.generate_report import generate_report_node
from .nodes.portfolio_ops import portfolio_ops_node
from .nodes.router import router_node
from .state import InvestmentAnalystState


def _route_after_router(
    state: InvestmentAnalystState,
) -> Literal["fetch_data", "portfolio_ops", "chat"]:
    intent = state.get("intent", "conversational")
    if intent in ("full_report", "single_ticker"):
        return "fetch_data"
    if intent in ("list_portfolio", "add_position", "remove_position"):
        return "portfolio_ops"
    return "chat"


def _route_after_analyze(
    state: InvestmentAnalystState,
) -> Literal["analyze_ticker", "generate_report"]:
    analyzed = set(state.get("ticker_analyses", {}).keys())
    remaining = [t for t in state.get("tickers_to_analyze", []) if t not in analyzed]
    if remaining:
        return "analyze_ticker"
    return "generate_report"


def build_graph(mcp_tools: dict) -> StateGraph:
    graph = StateGraph(InvestmentAnalystState)

    # Bind MCP tools into nodes that need them
    fetch_node = partial(fetch_data_node, mcp_tools=mcp_tools)
    chat_node_bound = partial(chat_node, mcp_tools=mcp_tools)
    portfolio_node_bound = partial(portfolio_ops_node, mcp_tools=mcp_tools)

    graph.add_node("router", router_node)
    graph.add_node("fetch_data", fetch_node)
    graph.add_node("analyze_ticker", analyze_ticker_node)
    graph.add_node("generate_report", generate_report_node)
    graph.add_node("chat", chat_node_bound)
    graph.add_node("portfolio_ops", portfolio_node_bound)

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        _route_after_router,
        {
            "fetch_data": "fetch_data",
            "portfolio_ops": "portfolio_ops",
            "chat": "chat",
        },
    )

    graph.add_edge("fetch_data", "analyze_ticker")

    graph.add_conditional_edges(
        "analyze_ticker",
        _route_after_analyze,
        {
            "analyze_ticker": "analyze_ticker",
            "generate_report": "generate_report",
        },
    )

    graph.add_edge("generate_report", END)
    graph.add_edge("chat", END)
    graph.add_edge("portfolio_ops", END)

    return graph
