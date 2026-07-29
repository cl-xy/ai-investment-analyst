"""
Chaos injection module for ops dashboard.

Allows toggling failure scenarios in non-production testing to validate
resilience: LLM timeouts, MCP tool failures, rate limit exhaustion,
and artificial slowdowns.

Integration points check chaos state before real calls. Auth-gated
so only demo-authenticated requests can toggle chaos.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from src.logging_config import get_logger

log = get_logger("ops.chaos")


@dataclass
class ChaosScenario:
    """A single chaos failure scenario."""

    enabled: bool = False
    activated_at: float | None = None
    description: str = ""


@dataclass
class ChaosConfig:
    """Global chaos configuration. Thread-safe access."""

    _lock: threading.Lock = field(default_factory=threading.Lock)

    llm_timeout: ChaosScenario = field(
        default_factory=lambda: ChaosScenario(
            description="Simulate LLM API timeout (30s delay before responding)"
        )
    )
    mcp_failure: ChaosScenario = field(
        default_factory=lambda: ChaosScenario(
            description="Simulate MCP tool server failures (all tool calls raise exceptions)"
        )
    )
    rate_limit_exhausted: ChaosScenario = field(
        default_factory=lambda: ChaosScenario(
            description="Simulate rate limiter exhaustion (all LLM calls rejected)"
        )
    )
    slow_response: ChaosScenario = field(
        default_factory=lambda: ChaosScenario(
            description="Add 5-10s artificial latency to all responses"
        )
    )

    def get_state(self) -> dict[str, Any]:
        """Return current chaos state as a serializable dict."""
        with self._lock:
            return {
                "llm_timeout": {
                    "enabled": self.llm_timeout.enabled,
                    "activated_at": self.llm_timeout.activated_at,
                    "description": self.llm_timeout.description,
                },
                "mcp_failure": {
                    "enabled": self.mcp_failure.enabled,
                    "activated_at": self.mcp_failure.activated_at,
                    "description": self.mcp_failure.description,
                },
                "rate_limit_exhausted": {
                    "enabled": self.rate_limit_exhausted.enabled,
                    "activated_at": self.rate_limit_exhausted.activated_at,
                    "description": self.rate_limit_exhausted.description,
                },
                "slow_response": {
                    "enabled": self.slow_response.enabled,
                    "activated_at": self.slow_response.activated_at,
                    "description": self.slow_response.description,
                },
            }

    def toggle(self, scenario_name: str, enabled: bool) -> bool:
        """
        Toggle a chaos scenario on/off.

        Returns True if the scenario was found and toggled, False otherwise.
        """
        scenario: ChaosScenario | None = getattr(self, scenario_name, None)
        if scenario is None or not isinstance(scenario, ChaosScenario):
            return False

        with self._lock:
            scenario.enabled = enabled
            scenario.activated_at = time.time() if enabled else None
            log.warning(
                "chaos_toggled",
                scenario=scenario_name,
                enabled=enabled,
            )
        return True

    def is_active(self, scenario_name: str) -> bool:
        """Check if a specific chaos scenario is currently active."""
        scenario: ChaosScenario | None = getattr(self, scenario_name, None)
        if scenario is None or not isinstance(scenario, ChaosScenario):
            return False
        with self._lock:
            return scenario.enabled

    def reset_all(self) -> None:
        """Disable all chaos scenarios."""
        with self._lock:
            for name in ("llm_timeout", "mcp_failure", "rate_limit_exhausted", "slow_response"):
                scenario = getattr(self, name)
                scenario.enabled = False
                scenario.activated_at = None
        log.info("chaos_reset_all")


# Singleton
chaos_config = ChaosConfig()


# Integration helpers: call these at integration points

async def check_llm_chaos() -> None:
    """
    Call before LLM API calls. Raises TimeoutError if llm_timeout is active,
    or raises RuntimeError if rate_limit_exhausted is active.
    """
    if chaos_config.is_active("rate_limit_exhausted"):
        raise RuntimeError("Chaos: rate limit exhausted (injected failure)")
    if chaos_config.is_active("llm_timeout"):
        # Simulate a slow response that will likely trigger timeout handling
        await asyncio.sleep(30.0)
        raise TimeoutError("Chaos: LLM timeout (injected failure)")


async def check_mcp_chaos() -> None:
    """Call before MCP tool execution. Raises RuntimeError if mcp_failure is active."""
    if chaos_config.is_active("mcp_failure"):
        raise RuntimeError("Chaos: MCP tool failure (injected failure)")


async def check_slow_response() -> None:
    """Call at response boundaries. Adds artificial latency if slow_response is active."""
    if chaos_config.is_active("slow_response"):
        import random

        delay = random.uniform(5.0, 10.0)
        await asyncio.sleep(delay)
