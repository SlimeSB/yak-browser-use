"""Tests for engine._harness.iteration_budget — LLM round-trip budget."""

from __future__ import annotations

import pytest

from yak_browser_use.engine._harness.iteration_budget import IterationBudget


class TestIterationBudget:
    def test_default_max_total(self):
        budget = IterationBudget()
        assert budget.max_total == 50
        assert budget.remaining == 50
        assert budget.used == 0

    def test_custom_max_total(self):
        budget = IterationBudget(max_total=100)
        assert budget.max_total == 100

    def test_min_total_enforced(self):
        with pytest.raises(ValueError, match="must be >= 10"):
            IterationBudget(max_total=5)

    def test_exact_min_total(self):
        budget = IterationBudget(max_total=10)
        assert budget.remaining == 10

    def test_consume_reduces_remaining(self):
        budget = IterationBudget(max_total=20)
        budget.consume(5)
        assert budget.remaining == 15
        assert budget.used == 5

    def test_consume_default_count(self):
        budget = IterationBudget(max_total=20)
        budget.consume()
        assert budget.remaining == 19

    def test_consume_does_not_go_below_zero(self):
        budget = IterationBudget(max_total=10)
        budget.consume(20)
        assert budget.remaining == 0

    def test_is_exhausted(self):
        budget = IterationBudget(max_total=10)
        assert budget.is_exhausted is False
        budget.consume(10)
        assert budget.is_exhausted is True

    def test_pause_and_resume(self):
        budget = IterationBudget(max_total=20)
        budget.pause()
        assert budget.is_paused is True
        budget.consume(10)  # should be ignored while paused
        assert budget.remaining == 20  # unchanged
        budget.resume()
        assert budget.is_paused is False
        budget.consume(5)
        assert budget.remaining == 15

    def test_reset(self):
        budget = IterationBudget(max_total=20)
        budget.consume(8)
        budget.pause()
        budget.reset()
        assert budget.remaining == 20
        assert budget.used == 0
        assert budget.is_paused is False

    def test_to_dict(self):
        budget = IterationBudget(max_total=30)
        budget.consume(5)
        d = budget.to_dict()
        assert d["max_total"] == 30
        assert d["used"] == 5
        assert d["remaining"] == 25
        assert d["paused"] is False

    def test_from_dict(self):
        d = {"max_total": 30, "used": 5, "remaining": 25, "paused": True}
        budget = IterationBudget.from_dict(d)
        assert budget.max_total == 30
        assert budget.used == 5
        assert budget.remaining == 25
        assert budget.is_paused is True

    def test_remaining_property(self):
        budget = IterationBudget(max_total=10)
        assert budget.remaining == 10
        budget.consume()
        assert budget.remaining == 9

    def test_used_property(self):
        budget = IterationBudget(max_total=10)
        budget.consume(3)
        assert budget.used == 3


class TestIterationBudgetIntegration:
    def test_full_lifecycle(self):
        budget = IterationBudget(max_total=50)

        # Simulate normal usage
        for _ in range(5):
            budget.consume()
        assert budget.remaining == 45

        # Pause for CDP reconnect
        budget.pause()
        for _ in range(10):
            budget.consume()  # ignored during pause
        assert budget.remaining == 45

        # Resume
        budget.resume()
        budget.consume(5)
        assert budget.remaining == 40

        # Serialize and restore
        restored = IterationBudget.from_dict(budget.to_dict())
        assert restored.remaining == 40
        assert restored.used == 10
