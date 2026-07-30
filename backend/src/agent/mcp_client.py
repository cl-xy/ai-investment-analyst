"""
Initializes MultiServerMCPClient connecting to all five MCP servers via stdio transport.
Call `get_mcp_tools_from_client()` inside the agent's async context to retrieve
LangChain-compatible tools.
"""

import logging
import os
import shutil
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

log = logging.getLogger(__name__)

# Backend root: MCP subprocesses must run from here so `src.*` imports resolve
_BACKEND_ROOT = str(Path(__file__).resolve().parents[2])

# Use the PATH-resolved python rather than sys.executable, because in Docker
# sys.executable may point to /usr/local/bin/python while the installed packages
# are available via /install/bin/python (first in PATH).
_PYTHON = shutil.which("python") or sys.executable

_MCP_MODULES = {
    "portfolio_server": "src.mcp_servers.portfolio_server.server",
    "market_server": "src.mcp_servers.market_server.server",
    "news_server": "src.mcp_servers.news_server.server",
    "sec_server": "src.mcp_servers.sec_server.server",
    "sentiment_server": "src.mcp_servers.sentiment_server.server",
}


def _build_server_config() -> dict:
    """Build a fresh MCP server config, capturing current environment."""
    env = os.environ.copy()
    return {
        name: {
            "command": _PYTHON,
            "args": ["-m", module],
            "transport": "stdio",
            "cwd": _BACKEND_ROOT,
            "env": env,
        }
        for name, module in _MCP_MODULES.items()
    }


def create_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(_build_server_config())  # type: ignore[arg-type]


async def get_mcp_tools_from_client(client: MultiServerMCPClient) -> dict:
    """Get tools dict from an already-connected client.

    Raises ValueError if duplicate tool names are detected across servers.
    """
    tools_list = await client.get_tools()
    tools: dict = {}
    for t in tools_list:
        if t.name in tools:
            raise ValueError(
                f"Duplicate MCP tool name '{t.name}' detected across servers. "
                "Tool names must be unique to avoid silent overwrites."
            )
        tools[t.name] = t
    return tools
