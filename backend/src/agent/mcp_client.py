"""
Initializes MultiServerMCPClient connecting to all four MCP servers via stdio transport.
Call `get_mcp_tools()` inside the agent's async context to retrieve LangChain-compatible tools.
"""

import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

# Project root: MCP subprocesses must run from here so `src.*` imports resolve
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)


def _server(module: str) -> dict:
    return {
        "command": sys.executable,
        "args": ["-m", module],
        "transport": "stdio",
        "cwd": _PROJECT_ROOT,
    }


MCP_SERVER_CONFIG = {
    "portfolio_server": _server("src.mcp_servers.portfolio_server.server"),
    "market_server": _server("src.mcp_servers.market_server.server"),
    "news_server": _server("src.mcp_servers.news_server.server"),
    "sec_server": _server("src.mcp_servers.sec_server.server"),
}


def create_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(MCP_SERVER_CONFIG)
