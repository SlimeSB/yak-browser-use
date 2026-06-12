"""Tests for iteration_budget module."""

import pytest

from engine._harness.iteration_budget import IterationBudget


def test_default_max_total():
    budget = IterationBudget()
    assert budget.max_total == 50
    assert budget.remaining == 50


def test_custom_max_total():
    budget = IterationBudget(max_total=20)
    assert budget.max_total == 20
    assert budget.remaining == 20


def test_min_total_enforced():
    with pytest.raises(ValueError, match="must be >= 10"):
        IterationBudget(max_total=5)


def test_consume():
    budget = IterationBudget(max_total=50)
    remaining = budget.consume(3)
    assert remaining == 47
    assert budget.used == 3


def test_consume_default_one():
    budget = IterationBudget(max_total=50)
    budget.consume()
    assert budget.used == 1


def test_is_exhausted():
    budget = IterationBudget(max_total=50)
    budget.consume(50)
    assert budget.is_exhausted
    assert budget.remaining == 0


def test_pause_resume():
    budget = IterationBudget(max_total=50)
    budget.consume(1)
    assert budget.used == 1

    budget.pause()
    assert budget.is_paused
    budget.consume(5)
    assert budget.used == 1  # not consumed while paused

    budget.resume()
    assert not budget.is_paused
    budget.consume(1)
    assert budget.used == 2


def test_reset():
    budget = IterationBudget(max_total=50)
    budget.consume(10)
    budget.pause()
    budget.reset()
    assert budget.used == 0
    assert budget.remaining == 50
    assert not budget.is_paused


def test_to_from_dict():
    budget = IterationBudget(max_total=30)
    budget.consume(5)
    budget.pause()
    d = budget.to_dict()
    assert d["max_total"] == 30
    assert d["used"] == 5
    assert d["paused"] is True

    restored = IterationBudget.from_dict(d)
    assert restored.max_total == 30
    assert restored.used == 5
    assert restored.is_paused
