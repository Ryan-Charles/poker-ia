from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class ZeroSumSolution:
    row_strategy: tuple[float, ...]
    column_strategy: tuple[float, ...]
    value: float
    exploitability: float
    iterations: int


def _regret_strategy(regrets: NDArray[np.float64]) -> NDArray[np.float64]:
    positive = np.maximum(regrets, 0.0)
    total = float(positive.sum())
    if total <= 0:
        return np.full(len(regrets), 1.0 / len(regrets), dtype=np.float64)
    return positive / total


def solve_zero_sum(payoff: NDArray[np.float64], *, iterations: int = 5_000) -> ZeroSumSolution:
    """Regret matching déterministe pour un sous-jeu matriciel zéro-somme.

    Ce solveur est réellement convergent sur les matrices finies, mais l'advisor ne
    lui transmet qu'une abstraction locale des actions/sizings, jamais l'arbre
    complet du No-Limit Hold'em.
    """

    matrix = np.asarray(payoff, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] < 1 or matrix.shape[1] < 1:
        raise ValueError("La matrice du sous-jeu doit être rectangulaire et non vide")
    if iterations < 1:
        raise ValueError("Le nombre d'itérations doit être positif")
    row_regrets = np.zeros(matrix.shape[0], dtype=np.float64)
    column_regrets = np.zeros(matrix.shape[1], dtype=np.float64)
    row_sum = np.zeros(matrix.shape[0], dtype=np.float64)
    column_sum = np.zeros(matrix.shape[1], dtype=np.float64)
    for _ in range(iterations):
        row = _regret_strategy(row_regrets)
        column = _regret_strategy(column_regrets)
        row_sum += row
        column_sum += column
        row_utilities = matrix @ column
        row_expected = float(row @ row_utilities)
        row_regrets += row_utilities - row_expected
        column_utilities = -(row @ matrix)
        column_expected = float(column @ column_utilities)
        column_regrets += column_utilities - column_expected
    average_row = row_sum / row_sum.sum()
    average_column = column_sum / column_sum.sum()
    value = float(average_row @ matrix @ average_column)
    best_row = float(np.max(matrix @ average_column))
    best_column = float(np.min(average_row @ matrix))
    exploitability = max(0.0, (best_row - best_column) / 2.0)
    return ZeroSumSolution(
        row_strategy=tuple(float(value) for value in average_row),
        column_strategy=tuple(float(value) for value in average_column),
        value=value,
        exploitability=exploitability,
        iterations=iterations,
    )
