from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from random import Random

from app.engine.cards import ensure_unique, full_deck
from app.engine.evaluator import evaluate_seven
from app.strategy.preflop import hand_strength


@dataclass(frozen=True, slots=True)
class RangeParameters:
    vpip: float = 0.28
    aggression: float = 0.38
    preflop_raise: bool = False


@dataclass(frozen=True, slots=True)
class EquityResult:
    equity: float
    win_rate: float
    tie_rate: float
    trials: int
    seed: int


def combo_weight(cards: tuple[str, str], parameters: RangeParameters) -> float:
    strength = hand_strength(cards)
    selectivity = max(0.08, min(0.95, parameters.vpip))
    exponent = 1.0 + (1.0 - selectivity) * 5.0
    weight = 0.02 + float(strength**exponent)
    if parameters.preflop_raise:
        weight *= 0.35 + strength * (0.9 + parameters.aggression)
    return float(max(0.001, weight))


def _sample_weighted_hand(
    deck: list[str], parameters: RangeParameters, rng: Random
) -> tuple[str, str]:
    candidate_count = min(36, len(deck) * (len(deck) - 1) // 2)
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    while len(candidates) < candidate_count:
        first, second = rng.sample(deck, 2)
        combo = (first, second) if first <= second else (second, first)
        if combo not in seen:
            seen.add(combo)
            candidates.append(combo)
    weights = [combo_weight(combo, parameters) for combo in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def estimate_equity(
    hero_cards: list[str],
    board: list[str],
    opponent_ranges: list[RangeParameters],
    *,
    dead_cards: list[str] | None = None,
    trials: int = 1_000,
    seed: int = 0,
) -> EquityResult:
    dead = dead_cards or []
    known = ensure_unique(hero_cards + board + dead)
    if len(hero_cards) != 2:
        raise ValueError("Deux cartes de Ryanchl sont requises pour calculer l'équité")
    if len(board) > 5:
        raise ValueError("Le board ne peut pas dépasser cinq cartes")
    if not opponent_ranges:
        return EquityResult(1.0, 1.0, 0.0, trials, seed)
    required_cards = len(opponent_ranges) * 2 + (5 - len(board))
    if required_cards > 52 - len(known):
        raise ValueError("Trop de cartes sont nécessaires pour les ranges demandées")
    rng = Random(seed)
    base_deck = [card for card in full_deck() if card not in set(known)]
    wins = 0
    ties = 0
    share_sum = 0.0
    for _ in range(trials):
        deck = list(base_deck)
        opponent_hands: list[tuple[str, str]] = []
        for parameters in opponent_ranges:
            hand = _sample_weighted_hand(deck, parameters, rng)
            opponent_hands.append(hand)
            deck.remove(hand[0])
            deck.remove(hand[1])
        runout = rng.sample(deck, 5 - len(board))
        complete_board = board + runout
        hero_key = evaluate_seven(hero_cards + complete_board).key
        opponent_keys = [evaluate_seven(list(hand) + complete_board).key for hand in opponent_hands]
        best = max([hero_key, *opponent_keys])
        if hero_key == best:
            tied_opponents = sum(key == best for key in opponent_keys)
            if tied_opponents == 0:
                wins += 1
                share_sum += 1.0
            else:
                ties += 1
                share_sum += 1.0 / (tied_opponents + 1)
    return EquityResult(
        equity=share_sum / trials,
        win_rate=wins / trials,
        tie_rate=ties / trials,
        trials=trials,
        seed=seed,
    )


def exact_heads_up_equity_on_river(hero_cards: list[str], board: list[str]) -> float:
    known = ensure_unique(hero_cards + board)
    if len(hero_cards) != 2 or len(board) != 5:
        raise ValueError(
            "Cette énumération exacte exige deux cartes privées et cinq cartes communes"
        )
    deck = [card for card in full_deck() if card not in set(known)]
    hero_key = evaluate_seven(hero_cards + board).key
    score = 0.0
    total = 0
    for opponent in combinations(deck, 2):
        opponent_key = evaluate_seven(list(opponent) + board).key
        total += 1
        if hero_key > opponent_key:
            score += 1.0
        elif hero_key == opponent_key:
            score += 0.5
    return score / total
