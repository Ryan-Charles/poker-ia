from __future__ import annotations

import numpy as np
import pytest

from app.strategy.local_solver import solve_zero_sum


def test_regret_matching_converges_on_matching_pennies() -> None:
    payoff = np.asarray([[1.0, -1.0], [-1.0, 1.0]])
    solution = solve_zero_sum(payoff, iterations=10_000)
    assert solution.row_strategy == pytest.approx((0.5, 0.5), abs=0.02)
    assert solution.column_strategy == pytest.approx((0.5, 0.5), abs=0.02)
    assert solution.value == pytest.approx(0.0, abs=0.02)
    assert solution.exploitability < 0.02


def test_solver_finds_dominant_action() -> None:
    payoff = np.asarray([[2.0, 1.0], [0.0, -1.0], [1.0, 0.0]])
    solution = solve_zero_sum(payoff, iterations=2_000)
    assert solution.row_strategy[0] > 0.98
    assert solution.value == pytest.approx(1.0, abs=0.02)


@pytest.mark.parametrize("iterations", [0, -1])
def test_solver_rejects_invalid_iterations(iterations: int) -> None:
    with pytest.raises(ValueError, match="positif"):
        solve_zero_sum(np.ones((2, 2)), iterations=iterations)
