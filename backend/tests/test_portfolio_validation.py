"""
Regression tests for portfolio position validation.

cost_basis of 0.0 means "unknown purchase price" and must be accepted so a
chat request like "add NVDA to my portfolio" (no price given) succeeds; shares
must still be strictly positive.
"""

import pytest

from src.mcp_servers.portfolio_server.server import (
    _validate_non_negative_float,
    _validate_positive_float,
)


def test_cost_basis_zero_is_accepted():
    assert _validate_non_negative_float(0.0, "cost_basis") == 0.0


def test_cost_basis_positive_is_accepted():
    assert _validate_non_negative_float(123.45, "cost_basis") == 123.45


def test_cost_basis_negative_is_rejected():
    with pytest.raises(ValueError):
        _validate_non_negative_float(-1.0, "cost_basis")


def test_shares_zero_is_rejected():
    with pytest.raises(ValueError):
        _validate_positive_float(0.0, "shares")


def test_shares_positive_is_accepted():
    assert _validate_positive_float(10.0, "shares") == 10.0
