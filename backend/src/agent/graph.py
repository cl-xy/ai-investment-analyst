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

from .nodes.chat import chat_node
from .nodes.compare import compare_node
from .nodes.debate import debate_ticker_node
from .nodes.fetch_data import fetch_data_node
from .nodes.generate_report import generate_report_node
from .nodes.peer_compare import peer_compare_node
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


def _route_after_debate(
    state: InvestmentAnalystState,
) -> Literal["debate", "peer_compare", "generate_report"]:
    analyzed = set(state.get("ticker_analyses", {}).keys())
    remaining = [t for t in state.get("tickers_to_analyze", []) if t not in analyzed]
    if remaining:
        return "debate"
    # Auto sector-peer comparison only makes sense for a single analyzed ticker.
    if len(state.get("tickers_to_analyze", [])) == 1:
        return "peer_compare"
    return "generate_report"


def build_graph(mcp_tools: dict) -> StateGraph:
    graph = StateGraph(InvestmentAnalystState)

    # Bind MCP tools into nodes that need them
    fetch_node = partial(fetch_data_node, mcp_tools=mcp_tools)
    chat_node_bound = partial(chat_node, mcp_tools=mcp_tools)
    portfolio_node_bound = partial(portfolio_ops_node, mcp_tools=mcp_tools)

    graph.add_node("router", router_node)
    graph.add_node("fetch_data", fetch_node)
    graph.add_node("debate", debate_ticker_node)
    graph.add_node("peer_compare", peer_compare_node)
    graph.add_node("generate_report", generate_report_node)
    graph.add_node("compare", compare_node)
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

    graph.add_edge("fetch_data", "debate")

    graph.add_conditional_edges(
        "debate",
        _route_after_debate,
        {
            "debate": "debate",
            "peer_compare": "peer_compare",
            "generate_report": "generate_report",
        },
    )
    graph.add_edge("peer_compare", "generate_report")

    def _route_after_report(state: InvestmentAnalystState) -> Literal["compare", "__end__"]:
        """Run comparison when multiple tickers were analyzed."""
        analyses = state.get("ticker_analyses", {})
        if len(analyses) >= 2:
            return "compare"
        return "__end__"

    graph.add_conditional_edges(
        "generate_report",
        _route_after_report,
        {
            "compare": "compare",
            "__end__": END,
        },
    )
    graph.add_edge("compare", END)
    graph.add_edge("chat", END)
    graph.add_edge("portfolio_ops", END)

    return graph
