"""
FastAPI application entry point for the Investment Analyst API.

Start with:
    uvicorn src.api.main:app --reload
or via the project script:
    serve
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.middleware.auth import DemoAuthMiddleware

from .routes.analyze import router as analyze_router
from .routes.analyze_stream import router as analyze_stream_router
from .routes.admin import router as admin_router
from .routes.eval import router as eval_router
from .routes.dashboard import router as dashboard_router
from .routes.explore import router as explore_router
from .routes.health import router as health_router
from .routes.scheduled import router as scheduled_router

app = FastAPI(
    title="Investment Analyst API",
    description="Multi-agent investment analysis with LangGraph orchestration and MCP tool servers.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DemoAuthMiddleware)

app.include_router(health_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(analyze_stream_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(eval_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(explore_router, prefix="/api")
app.include_router(scheduled_router, prefix="/api")


def start() -> None:
    """Entry point for `serve` script in pyproject.toml."""
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    start()
