"""
FastAPI application entry point for the Investment Analyst API.

Start with:
    uvicorn src.api.main:app --reload
or via the project script:
    serve
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Initialize structured logging (JSON in production, console in dev)
# Production runs on Fly.io with PORT=8000; use env var to detect environment.
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.config import settings
from src.db import close_pool, init_schema
from src.logging_config import get_logger, setup_logging
from src.metrics import router as metrics_router
from src.middleware.auth import DemoAuthMiddleware, limiter
from src.middleware.request_id import RequestIDMiddleware
from src.middleware.security_headers import SecurityHeadersMiddleware

from .routes.admin import router as admin_router
from .routes.analyze import router as analyze_router
from .routes.analyze_stream import router as analyze_stream_router
from .routes.backtest import router as backtest_router
from .routes.calibration import router as calibration_router
from .routes.chat import router as chat_router
from .routes.compare import router as compare_router
from .routes.dashboard import router as dashboard_router
from .routes.eval import router as eval_router
from .routes.explore import router as explore_router
from .routes.health import router as health_router
from .routes.ops import router as ops_router
from .routes.replay import router as replay_router
from .routes.scheduled import router as scheduled_router

_is_production = os.environ.get("FLY_APP_NAME") is not None
setup_logging(json_output=_is_production, level="INFO")
log = get_logger("app")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Initialize DB, load tools on startup. Clean up on shutdown."""

    from src.agent.direct_tools import _TOOL_EXECUTOR, load_direct_tools

    log.info("starting", version="0.2.0")

    # Set bounded thread pool as default executor so asyncio.to_thread uses it.
    # Prevents thread exhaustion on low-CPU deployments (Fly.io shared-cpu-1x).
    asyncio.get_running_loop().set_default_executor(_TOOL_EXECUTOR)

    await init_schema()
    log.info("database_ready")

    # Load tools directly in-process (no subprocess MCP servers)
    app.state.mcp_client = None
    app.state.mcp_tools = load_direct_tools()
    log.info("tools_ready", count=len(app.state.mcp_tools))

    try:
        yield
    finally:
        _TOOL_EXECUTOR.shutdown(wait=True, cancel_futures=True)
        await close_pool()
        log.info("shutdown_complete")


app = FastAPI(
    title="Investment Analyst API",
    description="Multi-agent investment analysis with LangGraph orchestration and MCP tool servers.",
    version="0.2.0",
    lifespan=_lifespan,
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(DemoAuthMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(analyze_stream_router, prefix="/api")
app.include_router(backtest_router, prefix="/api")
app.include_router(calibration_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(eval_router, prefix="/api")
app.include_router(compare_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(explore_router, prefix="/api")
app.include_router(replay_router, prefix="/api")
app.include_router(scheduled_router, prefix="/api")
app.include_router(ops_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")


def start() -> None:
    """Entry point for `serve` script in pyproject.toml."""
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=not _is_production,
    )


if __name__ == "__main__":
    start()
