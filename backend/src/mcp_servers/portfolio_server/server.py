from dotenv import load_dotenv

load_dotenv()

from fastmcp import FastMCP

from .db import (
    delete_position,
    fetch_all_positions,
    update_position_fields,
    upsert_position,
)

mcp = FastMCP("portfolio-server")


@mcp.tool()
async def get_portfolio() -> list[dict]:
    """Return all portfolio positions with ticker, shares, cost_basis, sector, added_date."""
    return await fetch_all_positions()


@mcp.tool()
async def add_position(
    ticker: str, shares: float, cost_basis: float, sector: str = "Unknown"
) -> dict:
    """Add or replace a position. cost_basis is the average purchase price per share."""
    await upsert_position(ticker, shares, cost_basis, sector)
    return {
        "success": True,
        "message": f"Position {ticker.upper()} saved ({shares} shares @ ${cost_basis:.2f})",
    }


@mcp.tool()
async def remove_position(ticker: str) -> dict:
    """Remove a position from the portfolio."""
    removed = await delete_position(ticker)
    if removed:
        return {"success": True, "message": f"{ticker.upper()} removed from portfolio"}
    return {"success": False, "message": f"{ticker.upper()} not found in portfolio"}


@mcp.tool()
async def update_position(
    ticker: str, shares: float | None = None, cost_basis: float | None = None
) -> dict:
    """Update shares and/or cost_basis for an existing position."""
    updated = await update_position_fields(ticker, shares, cost_basis)
    if updated:
        return {"success": True, "message": f"{ticker.upper()} updated"}
    return {"success": False, "message": f"{ticker.upper()} not found or no changes provided"}


@mcp.tool()
async def get_portfolio_value(prices: dict[str, float]) -> dict:
    """
    Compute portfolio value given a prices dict {ticker: current_price}.
    Returns total_value, total_cost, unrealized_gain_pct, and per-position breakdown.
    """
    positions = await fetch_all_positions()
    breakdown = []
    total_value = 0.0
    total_cost = 0.0
    for pos in positions:
        ticker = pos["ticker"]
        price = prices.get(ticker)
        position_cost = pos["shares"] * pos["cost_basis"]
        total_cost += position_cost
        if price is not None:
            position_value = pos["shares"] * price
            total_value += position_value
            gain_pct = (
                (price - pos["cost_basis"]) / pos["cost_basis"] * 100 if pos["cost_basis"] else 0.0
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
            breakdown.append(
                {**pos, "current_price": None, "position_value": None, "gain_pct": None}
            )
    unrealized_gain_pct = (total_value - total_cost) / total_cost * 100 if total_cost else 0.0
    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "unrealized_gain_pct": unrealized_gain_pct,
        "positions": breakdown,
    }


if __name__ == "__main__":
    mcp.run()
