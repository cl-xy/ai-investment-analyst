"""
Static sector -> large-cap ticker map used for auto peer/sector comparison.

Kept as a small curated list rather than a dynamic lookup so peer discovery
never costs an extra network call. Sector strings match yfinance's
`info.get("sector")` values (GICS-style sector names). This will drift over
time (M&A, reclassification) and is meant as a "good enough" heuristic, not
an authoritative sector taxonomy.
"""

SECTOR_PEERS: dict[str, tuple[str, ...]] = {
    "Technology": ("AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "ADBE", "CSCO"),
    "Financial Services": ("JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "AXP"),
    "Healthcare": ("UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT"),
    "Consumer Cyclical": ("AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "TJX"),
    "Communication Services": ("GOOGL", "META", "NFLX", "DIS", "CMCSA", "TMUS", "VZ", "T"),
    "Energy": ("XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "OXY"),
    "Industrials": ("GE", "CAT", "RTX", "HON", "UPS", "BA", "UNP", "LMT"),
    "Consumer Defensive": ("WMT", "PG", "KO", "PEP", "COST", "PM", "MDLZ", "CL"),
    "Utilities": ("NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL"),
    "Real Estate": ("PLD", "AMT", "EQIX", "PSA", "O", "SPG", "WELL", "DLR"),
    "Basic Materials": ("LIN", "SHW", "FCX", "APD", "ECL", "NEM", "NUE", "DD"),
}

# yfinance sometimes returns GICS-style names that differ from our keys.
# Map known variants to the canonical key used in SECTOR_PEERS.
_SECTOR_ALIASES: dict[str, str] = {
    "Information Technology": "Technology",
    "Financials": "Financial Services",
    "Health Care": "Healthcare",
    "Consumer Discretionary": "Consumer Cyclical",
    "Consumer Staples": "Consumer Defensive",
    "Materials": "Basic Materials",
}


def get_sector_peers(sector: str | None, exclude: set[str], limit: int = 2) -> list[str]:
    """Return up to `limit` peer tickers for a sector, excluding `exclude`.

    Returns an empty list if the sector is unknown/missing rather than
    guessing, or if limit is non-positive.
    """
    if not sector or limit <= 0:
        return []
    normalized = sector.strip()
    canonical = _SECTOR_ALIASES.get(normalized, normalized)
    candidates = SECTOR_PEERS.get(canonical, ())
    exclude_upper = {t.upper() for t in exclude}
    return [t for t in candidates if t.upper() not in exclude_upper][:limit]
