import logging
import os
from functools import cache

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from ..state import InvestmentAnalystState

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10

CHAT_SYSTEM = """You are a knowledgeable investment analyst assistant. Help the user understand their portfolio and investment opportunities.

You have access to tools to fetch stock prices, news, fundamentals, SEC filings, and portfolio data.
Use them when the user asks about specific stocks or wants updated information.

Be concise and actionable. When citing data, note the source."""


@cache
def _get_llm() -> ChatOpenAI:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set")
    return ChatOpenAI(
        model="openai/gpt-oss-120b",
        temperature=0,
        max_tokens=4096,
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
        request_timeout=60,
    )


async def chat_node(state: InvestmentAnalystState, *, mcp_tools: dict) -> dict:
    tools = list(mcp_tools.values()) if mcp_tools else []
    llm = _get_llm()
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    messages = [SystemMessage(content=CHAT_SYSTEM)] + list(state["messages"])

    for _ in range(MAX_TOOL_ROUNDS):
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        # If no tool calls, we're done
        if not getattr(response, "tool_calls", None):
            break

        # Execute tool calls
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool = mcp_tools.get(tool_name)
            if tool:
                try:
                    result = await tool.ainvoke(tool_call["args"])
                    messages.append(
                        ToolMessage(
                            content=str(result),
                            tool_call_id=tool_call["id"],
                        )
                    )
                except Exception as e:
                    messages.append(
                        ToolMessage(
                            content=f"Error calling {tool_name}: {e}",
                            tool_call_id=tool_call["id"],
                        )
                    )
    else:
        # Tool loop hit the limit without a natural break
        log.warning("chat_node hit MAX_TOOL_ROUNDS (%d)", MAX_TOOL_ROUNDS)
        from langchain_core.messages import AIMessage

        messages.append(
            AIMessage(
                content="I've reached the maximum number of tool calls for this turn. Here's what I have so far based on the information gathered above."
            )
        )

    # Return only the new messages (everything after the original state messages)
    new_messages = messages[1 + len(state["messages"]) :]  # skip the SystemMessage offset
    return {"messages": new_messages}
