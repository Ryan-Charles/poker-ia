from __future__ import annotations

from dataclasses import dataclass

from app.engine.cards import canonical_hole_class, parse_card
from app.models import ActionKind

PREFLOP_TABLE_VERSION = "preflop-fr-1.0"
DEPTH_BUCKETS = (10, 15, 20, 25, 40, 60, 80, 100, 150, 200)

# Pourcentages de mains jouées dans l'abstraction de référence. Les valeurs sont
# versionnées et déterministes; elles ne prétendent pas reproduire un solveur exact.
OPEN_THRESHOLDS: dict[str, dict[int, float]] = {
    "UTG": {
        10: 0.22,
        15: 0.20,
        20: 0.19,
        25: 0.18,
        40: 0.17,
        60: 0.17,
        80: 0.17,
        100: 0.17,
        150: 0.16,
        200: 0.16,
    },
    "UTG+1": {
        10: 0.25,
        15: 0.23,
        20: 0.22,
        25: 0.21,
        40: 0.20,
        60: 0.20,
        80: 0.20,
        100: 0.20,
        150: 0.19,
        200: 0.19,
    },
    "MP": {
        10: 0.29,
        15: 0.27,
        20: 0.26,
        25: 0.25,
        40: 0.24,
        60: 0.24,
        80: 0.24,
        100: 0.24,
        150: 0.23,
        200: 0.23,
    },
    "HJ": {
        10: 0.35,
        15: 0.33,
        20: 0.32,
        25: 0.31,
        40: 0.30,
        60: 0.30,
        80: 0.30,
        100: 0.30,
        150: 0.29,
        200: 0.29,
    },
    "CO": {
        10: 0.46,
        15: 0.44,
        20: 0.43,
        25: 0.42,
        40: 0.40,
        60: 0.40,
        80: 0.40,
        100: 0.40,
        150: 0.39,
        200: 0.39,
    },
    "BTN": {
        10: 0.60,
        15: 0.58,
        20: 0.56,
        25: 0.55,
        40: 0.53,
        60: 0.52,
        80: 0.52,
        100: 0.52,
        150: 0.50,
        200: 0.50,
    },
    "BTN/SB": {
        10: 0.72,
        15: 0.69,
        20: 0.67,
        25: 0.65,
        40: 0.63,
        60: 0.62,
        80: 0.62,
        100: 0.61,
        150: 0.60,
        200: 0.60,
    },
    "SB": {
        10: 0.55,
        15: 0.52,
        20: 0.50,
        25: 0.49,
        40: 0.47,
        60: 0.46,
        80: 0.46,
        100: 0.45,
        150: 0.44,
        200: 0.44,
    },
    "BB": {
        10: 0.52,
        15: 0.50,
        20: 0.48,
        25: 0.47,
        40: 0.45,
        60: 0.44,
        80: 0.44,
        100: 0.43,
        150: 0.42,
        200: 0.42,
    },
}


@dataclass(frozen=True, slots=True)
class PreflopDecision:
    action: ActionKind
    raise_bb: float | None
    mix: dict[ActionKind, float]
    hand_class: str
    strength: float
    depth_bucket: int
    table_version: str = PREFLOP_TABLE_VERSION


def depth_bucket(big_blinds: float) -> int:
    return min(DEPTH_BUCKETS, key=lambda depth: abs(depth - big_blinds))


def interpolate_threshold(position: str, big_blinds: float) -> float:
    table = OPEN_THRESHOLDS.get(position, OPEN_THRESHOLDS["MP"])
    if big_blinds <= DEPTH_BUCKETS[0]:
        return table[DEPTH_BUCKETS[0]]
    if big_blinds >= DEPTH_BUCKETS[-1]:
        return table[DEPTH_BUCKETS[-1]]
    lower = max(depth for depth in DEPTH_BUCKETS if depth <= big_blinds)
    upper = min(depth for depth in DEPTH_BUCKETS if depth >= big_blinds)
    if lower == upper:
        return table[lower]
    ratio = (big_blinds - lower) / (upper - lower)
    return table[lower] + (table[upper] - table[lower]) * ratio


def hand_strength(cards: list[str] | tuple[str, str]) -> float:
    first, second = (parse_card(card) for card in cards)
    high, low = sorted((first.value, second.value), reverse=True)
    if high == low:
        return min(1.0, 0.50 + (high - 2) / 12 * 0.50)
    score = (high - 2) / 12 * 0.56 + (low - 2) / 12 * 0.24
    if first.suit == second.suit:
        score += 0.08
    gap = high - low - 1
    score += max(0.0, 0.08 - max(0, gap) * 0.018)
    if high == 14:
        score += 0.05
    if low <= 5 and high <= 7:
        score += 0.02
    return max(0.01, min(0.99, score))


def chart_decision(
    cards: list[str],
    *,
    position: str,
    stack_bb: float,
    facing_raise: bool,
    raise_count: int,
) -> PreflopDecision:
    strength = hand_strength(cards)
    playable_fraction = interpolate_threshold(position, stack_bb)
    required = 1.0 - playable_fraction
    bucket = depth_bucket(stack_bb)
    hand_class = canonical_hole_class(cards)
    if facing_raise:
        continue_required = min(0.91, required + 0.16 + 0.05 * max(0, raise_count - 1))
        reraise_required = min(0.96, continue_required + 0.10)
        if strength >= reraise_required:
            action = ActionKind.RAISE
            mix = {ActionKind.RAISE: 0.72, ActionKind.CALL: 0.28}
        elif strength >= continue_required:
            action = ActionKind.CALL
            mix = {ActionKind.CALL: 0.72, ActionKind.RAISE: 0.12, ActionKind.FOLD: 0.16}
        else:
            action = ActionKind.FOLD
            mix = {ActionKind.FOLD: 0.94, ActionKind.CALL: 0.06}
    elif strength >= required + 0.18:
        action = ActionKind.RAISE
        mix = {ActionKind.RAISE: 0.88, ActionKind.CALL: 0.12}
    elif strength >= required:
        action = ActionKind.RAISE
        mix = {ActionKind.RAISE: 0.62, ActionKind.CALL: 0.23, ActionKind.FOLD: 0.15}
    else:
        action = ActionKind.CHECK if position == "BB" else ActionKind.FOLD
        mix = {action: 0.94, ActionKind.RAISE: 0.06}
    raise_bb = 2.2 if stack_bb <= 25 else 2.5
    return PreflopDecision(action, raise_bb, mix, hand_class, strength, bucket)
