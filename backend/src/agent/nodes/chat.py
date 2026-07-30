from langchain_core.messages import SystemMessage, ToolMessage

from src.logging_config import get_logger

from ..llm_fallback import invoke_with_fallback
from ..state import InvestmentAnalystState

log = get_logger(__name__)

MAX_TOOL_ROUNDS = 10

CHAT_SYSTEM = """You are a knowledgeable investment analyst assistant. Help the user understand their portfolio and investment opportunities.

You have access to tools to fetch stock prices, news, fundamentals, SEC filings, and portfolio data.
Use them when the user asks about specific stocks or wants updated information.

Be concise and actionable. When citing data, note the source."""


async def chat_node(state: InvestmentAnalystState, *, mcp_tools: dict) -> dict:
    mcp_tools = mcp_tools or {}
    tools = list(mcp_tools.values()) if mcp_tools else []
    correlation_id = state.get("correlation_id")
    _log = log.bind(correlation_id=correlation_id, node="chat") if correlation_id else log

    messages = [SystemMessage(content=CHAT_SYSTEM)] + list(state["messages"])

    for _ in range(MAX_TOOL_ROUNDS):
        response = await invoke_with_fallback(
            messages,
            temperature=0,
            max_tokens=8192,
            request_timeout=120,
            json_mode=False,
            tools=tools or None,
        )
        messages.append(response)

        # If no tool calls, we're done
        if not getattr(response, "tool_calls", None):
            break

        # Execute tool calls
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool = mcp_tools.get(tool_name)
            if tool is not None:
                try:
                    result = await tool.ainvoke(tool_call["args"])
                    messages.append(
                        ToolMessage(
                            content=str(result),
                            tool_call_id=tool_call["id"],
                        )
                    )
                except Exception as e:
                    _log.error(
                        "chat_tool_error",
                        tool=tool_name,
                        error=str(e),
                    )
                    messages.append(
                        ToolMessage(
                            content=f"Error: tool '{tool_name}' failed to execute.",
                            tool_call_id=tool_call["id"],
                        )
                    )
            else:
                _log.warning("chat_tool_not_found", tool=tool_name)
                messages.append(
                    ToolMessage(
                        content=f"Error: tool '{tool_name}' is not available.",
                        tool_call_id=tool_call["id"],
                    )
                )
    else:
        # Tool loop hit the limit without a natural break
        _log.warning("chat_node_max_tool_rounds", max_rounds=MAX_TOOL_ROUNDS)
        from langchain_core.messages import AIMessage

        messages.append(
            AIMessage(
                content="I've reached the maximum number of tool calls for this turn. Here's what I have so far based on the information gathered above."
            )
        )

    # Return only the new messages (everything after the original state messages)
    new_messages = messages[1 + len(state["messages"]) :]  # skip the SystemMessage offset
    return {"messages": new_messages}
