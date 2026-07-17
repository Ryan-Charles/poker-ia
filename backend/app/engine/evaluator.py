from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from app.engine.cards import Card, ensure_unique, parse_card
from app.engine.pokerkit_adapter import validate_standard_high

CATEGORY_NAMES = {
    0: "carte haute",
    1: "paire",
    2: "double paire",
    3: "brelan",
    4: "quinte",
    5: "couleur",
    6: "full",
    7: "carré",
    8: "quinte flush",
}


@dataclass(frozen=True, slots=True)
class EvaluatedHand:
    key: tuple[int, ...]
    name: str
    cards: tuple[str, ...]

    @property
    def category(self) -> int:
        return self.key[0]


def _straight_high(unique_values: set[int]) -> int | None:
    values = set(unique_values)
    if 14 in values:
        values.add(1)
    for high in range(14, 4, -1):
        if all(value in values for value in range(high - 4, high + 1)):
            return high
    return None


def evaluate_five(cards: list[str] | tuple[str, ...]) -> EvaluatedHand:
    normalized = ensure_unique(cards)
    if len(normalized) != 5:
        raise ValueError("L'évaluation à cinq cartes exige exactement cinq cartes")
    parsed = [parse_card(card) for card in normalized]
    values = [card.value for card in parsed]
    counts: dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    groups = sorted(((count, value) for value, count in counts.items()), reverse=True)
    flush = len({card.suit for card in parsed}) == 1
    straight_high = _straight_high(set(values))
    key: tuple[int, ...]

    if flush and straight_high is not None:
        key = (8, straight_high)
        name = "quinte flush royale" if straight_high == 14 else CATEGORY_NAMES[8]
    elif groups[0][0] == 4:
        quad = groups[0][1]
        kicker = max(value for value in values if value != quad)
        key = (7, quad, kicker)
        name = CATEGORY_NAMES[7]
    elif groups[0][0] == 3 and groups[1][0] == 2:
        key = (6, groups[0][1], groups[1][1])
        name = CATEGORY_NAMES[6]
    elif flush:
        key = (5, *sorted(values, reverse=True))
        name = CATEGORY_NAMES[5]
    elif straight_high is not None:
        key = (4, straight_high)
        name = CATEGORY_NAMES[4]
    elif groups[0][0] == 3:
        trips = groups[0][1]
        kickers = sorted((value for value in values if value != trips), reverse=True)
        key = (3, trips, *kickers)
        name = CATEGORY_NAMES[3]
    elif groups[0][0] == 2 and groups[1][0] == 2:
        pairs = sorted((groups[0][1], groups[1][1]), reverse=True)
        kicker = max(value for value in values if value not in pairs)
        key = (2, *pairs, kicker)
        name = CATEGORY_NAMES[2]
    elif groups[0][0] == 2:
        pair = groups[0][1]
        kickers = sorted((value for value in values if value != pair), reverse=True)
        key = (1, pair, *kickers)
        name = CATEGORY_NAMES[1]
    else:
        key = (0, *sorted(values, reverse=True))
        name = CATEGORY_NAMES[0]
    ordered_cards = tuple(card.code for card in sorted(parsed, key=_display_sort, reverse=True))
    return EvaluatedHand(key=key, name=name, cards=ordered_cards)


def _display_sort(card: Card) -> tuple[int, str]:
    return card.value, card.suit


def evaluate_seven(cards: list[str] | tuple[str, ...]) -> EvaluatedHand:
    normalized = ensure_unique(cards)
    if not 5 <= len(normalized) <= 7:
        raise ValueError("L'évaluation Hold'em exige de cinq à sept cartes connues")
    best = max(
        (evaluate_five(combo) for combo in combinations(normalized, 5)), key=lambda hand: hand.key
    )
    validate_standard_high(best.cards)
    return best
