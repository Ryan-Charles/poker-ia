from __future__ import annotations

import pytest

from app.engine.cards import CardError, canonical_hole_class, ensure_unique, normalize_card
from app.engine.evaluator import evaluate_five, evaluate_seven
from app.engine.pokerkit_adapter import validate_standard_high


@pytest.mark.parametrize(
    ("cards", "name", "category"),
    [
        (["As", "Kd", "9h", "5c", "3d"], "carte haute", 0),
        (["As", "Ad", "9h", "5c", "3d"], "paire", 1),
        (["As", "Ad", "9h", "9c", "3d"], "double paire", 2),
        (["As", "Ad", "Ah", "9c", "3d"], "brelan", 3),
        (["As", "2d", "3h", "4c", "5d"], "quinte", 4),
        (["As", "Js", "9s", "5s", "3s"], "couleur", 5),
        (["As", "Ad", "Ah", "9c", "9d"], "full", 6),
        (["As", "Ad", "Ah", "Ac", "9d"], "carré", 7),
        (["9s", "Ts", "Js", "Qs", "Ks"], "quinte flush", 8),
        (["Ts", "Js", "Qs", "Ks", "As"], "quinte flush royale", 8),
    ],
)
def test_all_hand_categories(cards: list[str], name: str, category: int) -> None:
    evaluated = evaluate_five(cards)
    assert evaluated.name == name
    assert evaluated.category == category


def test_pair_kicker_breaks_tie() -> None:
    board = ["Ah", "7d", "5c", "3s", "2h"]
    assert evaluate_seven(["Ad", "Kc", *board]).key > evaluate_seven(["Ac", "Qc", *board]).key


def test_board_can_play_entirely() -> None:
    board = ["As", "Ks", "Qs", "Js", "Ts"]
    hero = evaluate_seven(["2c", "3d", *board])
    villain = evaluate_seven(["9c", "9d", *board])
    assert hero.key == villain.key
    assert hero.name == "quinte flush royale"


def test_best_five_can_use_one_or_two_hole_cards() -> None:
    board = ["Ah", "Kd", "7s", "4c", "2d"]
    one = evaluate_seven(["As", "Qc", *board])
    two = evaluate_seven(["7h", "7d", *board])
    assert one.name == "paire"
    assert two.name == "brelan"


def test_card_normalization_and_classes() -> None:
    assert normalize_card("10♠") == "Ts"
    assert normalize_card("aH") == "Ah"
    assert canonical_hole_class(["As", "Ks"]) == "AKs"
    assert canonical_hole_class(["Ad", "Ac"]) == "AA"


def test_duplicates_are_rejected() -> None:
    with pytest.raises(CardError, match="même carte"):
        ensure_unique(["As", "AS"])


def test_pokerkit_adapter_is_really_available() -> None:
    validation = validate_standard_high(["As", "Ks", "Qs", "Js", "Ts"])
    assert validation.available is True
    assert validation.accepted is True
