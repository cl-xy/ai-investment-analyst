import math

from dotenv import load_dotenv

load_dotenv()

from fastmcp import FastMCP

from src.validation import validate_ticker

from .db import (
    delete_position,
    fetch_all_positions,
    update_position_fields,
    upsert_position,
)

mcp = FastMCP("portfolio-server")


def _validate_ticker(ticker: str) -> str:
    """Normalize and validate ticker. Returns uppercase ticker or raises ValueError."""
    return validate_ticker(ticker)


def _validate_positive_float(value: float, field: str) -> float:
    """Validate that value is a finite positive number (not bool)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field} must be a finite positive number")
    return value


def _validate_non_negative_float(value: float, field: str) -> float:
    """Validate that value is a finite non-negative number (not bool)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return value


@mcp.tool()
async def get_portfolio() -> list[dict]:
    """Return all portfolio positions with ticker, shares, cost_basis, sector, added_date."""
    try:
        return await fetch_all_positions()
    except Exception as e:
        return {"success": False, "error": f"Failed to fetch portfolio: {e}"}


@mcp.tool()
async def add_position(
    ticker: str, shares: float, cost_basis: float, sector: str = "Unknown"
) -> dict:
    """Add or replace a position. cost_basis is the average purchase price per share."""
    try:
        ticker = _validate_ticker(ticker)
        shares = _validate_positive_float(shares, "shares")
        cost_basis = _validate_positive_float(cost_basis, "cost_basis")
        if not isinstance(sector, str) or len(sector.strip()) == 0 or len(sector) > 50:
            sector = "Unknown"
        await upsert_position(ticker, shares, cost_basis, sector)
        return {
            "success": True,
            "message": f"Position {ticker} saved ({shares} shares @ ${cost_basis:.2f})",
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Failed to add position: {e}"}


@mcp.tool()
async def remove_position(ticker: str) -> dict:
    """Remove a position from the portfolio."""
    try:
        ticker = _validate_ticker(ticker)
        removed = await delete_position(ticker)
        if removed:
            return {"success": True, "message": f"{ticker} removed from portfolio"}
        return {"success": False, "message": f"{ticker} not found in portfolio"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Failed to remove position: {e}"}


@mcp.tool()
async def update_position(
    ticker: str, shares: float | None = None, cost_basis: float | None = None
) -> dict:
    """Update shares and/or cost_basis for an existing position."""
    try:
        ticker = _validate_ticker(ticker)
        if shares is None and cost_basis is None:
            return {"success": False, "error": "No fields provided to update"}
        if shares is not None:
            shares = _validate_positive_float(shares, "shares")
        if cost_basis is not None:
            cost_basis = _validate_positive_float(cost_basis, "cost_basis")
        updated = await update_position_fields(ticker, shares, cost_basis)
        if updated:
            return {"success": True, "message": f"{ticker} updated"}
        return {"success": False, "message": f"{ticker} not found"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Failed to update position: {e}"}


@mcp.tool()
async def get_portfolio_value(prices: dict[str, float]) -> dict:
    """
    Compute portfolio value given a prices dict {ticker: current_price}.
    Returns total_value, total_cost, unrealized_gain_pct, and per-position breakdown.
    Only positions with valid prices contribute to totals.
    """
    try:
        positions = await fetch_all_positions()
        # Normalize price dict keys for case-insensitive matching
        normalized_prices = {}
        for k, v in prices.items():
            if isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool):
                v_float = float(v)
                if math.isfinite(v_float) and v_float >= 0:
                    normalized_prices[k.strip().upper()] = v_float

        breakdown = []
        total_value = 0.0
        total_cost = 0.0
        missing_prices = []

        for pos in positions:
            ticker = pos["ticker"]
            normalized_ticker = ticker.strip().upper() if isinstance(ticker, str) else ticker
            price = normalized_prices.get(normalized_ticker)
            position_cost = pos["shares"] * pos["cost_basis"]

            if price is not None:
                position_value = pos["shares"] * price
                total_value += position_value
                total_cost += position_cost
                gain_pct = (
                    (price - pos["cost_basis"]) / pos["cost_basis"] * 100
                    if pos["cost_basis"]
                    else None
                )
                breakdown.append(
                    {
                        **pos,
                        "current_price": price,
                        "position_value": position_value,
                        "gain_pct": gain_pct,
                    }
                )
            else:
                missing_prices.append(normalized_ticker)
                breakdown.append(
                    {**pos, "current_price": None, "position_value": None, "gain_pct": None}
                )

        unrealized_gain_pct = (
            (total_value - total_cost) / total_cost * 100 if total_cost else 0.0
        )
        return {
            "total_value": total_value,
            "total_cost": total_cost,
            "unrealized_gain_pct": unrealized_gain_pct,
            "positions": breakdown,
            "missing_prices": missing_prices,
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to compute portfolio value: {e}"}


if __name__ == "__main__":
    mcp.run()
