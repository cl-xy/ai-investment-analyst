"""
Initializes MultiServerMCPClient connecting to all four MCP servers via stdio transport.
Call `get_mcp_tools()` inside the agent's async context to retrieve LangChain-compatible tools.
"""

import os
import shutil
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

# Project root: MCP subprocesses must run from here so `src.*` imports resolve
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)

# Use the PATH-resolved python rather than sys.executable, because in Docker
# sys.executable may point to /usr/local/bin/python while the installed packages
# are available via /install/bin/python (first in PATH).
_PYTHON = shutil.which("python") or sys.executable


def _server(module: str) -> dict:
    env = os.environ.copy()
    return {
        "command": _PYTHON,
        "args": ["-m", module],
        "transport": "stdio",
        "cwd": _PROJECT_ROOT,
        "env": env,
    }


MCP_SERVER_CONFIG = {
    "portfolio_server": _server("src.mcp_servers.portfolio_server.server"),
    "market_server": _server("src.mcp_servers.market_server.server"),
    "news_server": _server("src.mcp_servers.news_server.server"),
    "sec_server": _server("src.mcp_servers.sec_server.server"),
}


def create_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(MCP_SERVER_CONFIG)


async def get_mcp_tools_from_client(client: MultiServerMCPClient) -> dict:
    """Get tools dict from an already-connected client."""
    tools_list = await client.get_tools()
    return {t.name: t for t in tools_list}
