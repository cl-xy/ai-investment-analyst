"""Tests for the front-loaded per-turn budget allocation in the debate node.

Bull is the critical turn: its failure returns a total insufficient_data card,
while bear/moderator failures degrade in place. The budget allocator must give
bull enough room to abandon one stalled primary (capped at the attempt timeout,
~45s) and still reach a healthy fallback, without starving the moderator below
one useful call window.
"""

from src.agent.nodes.debate import _MIN_TURN_BUDGET, _turn_budget
from src.config import settings


def test_bull_gets_room_for_stall_plus_fallback():
    # With the full 165s ticker budget, the bull turn (turns_left=3) must be
    # large enough that a full attempt-timeout stall still leaves a real
    # fallback window inside the same turn.
    budget = _turn_budget(settings.debate_ticker_budget_seconds, turns_left=3)
    # One stalled primary (attempt timeout) + a useful fallback window.
    assert budget >= settings.llm_attempt_timeout_seconds + _MIN_TURN_BUDGET


def test_bull_is_front_loaded_vs_even_split():
    remaining = 165.0
    bull = _turn_budget(remaining, turns_left=3)
    # An even split would be remaining / 3 ~= 55s; bull must get strictly more.
    assert bull > remaining / 3


def test_moderator_never_starved_below_floor():
    # Even when little budget remains, the final turn gets at least the floor
    # (or whatever is left, if that is already below the floor).
    assert _turn_budget(20.0, turns_left=1) == 20.0  # less than floor -> all of it
    assert _turn_budget(100.0, turns_left=1) == 100.0  # weight 1.0 -> everything


def test_turn_budget_never_negative():
    assert _turn_budget(-5.0, turns_left=3) == 0.0
    assert _turn_budget(0.0, turns_left=2) == 0.0


def test_bear_takes_majority_of_remainder():
    # After bull consumes its slice, bear (turns_left=2) front-loads over moderator.
    remaining = 90.0
    bear = _turn_budget(remaining, turns_left=2)
    assert bear > remaining / 2
