from __future__ import annotations

from collections.abc import Callable

import pytest

from app.engine.holdem import HoldemEngine, PokerRuleError
from app.engine.pots import build_pots
from app.models import (
    ActionKind,
    ActionRequest,
    HandStatus,
    PlayerConfig,
    PlayerState,
    PlayerStatus,
    SessionCreate,
    ShowdownRequest,
)


def test_simple_showdown_computes_exact_net(make_config: Callable[..., SessionCreate]) -> None:
    engine = _heads_up_showdown(make_config(2), hero=("As", "Ad"), villain=("Ks", "Kd"))
    assert engine.state.result is not None
    assert engine.state.result.winners == ["hero"]
    assert engine.state.result.total_pot == 20
    assert engine.state.result.net_results["hero"] == 10
    assert engine.state.result.hand_ranks["hero"] == "paire"


def test_exact_tie_splits_pot_and_board_plays(make_config: Callable[..., SessionCreate]) -> None:
    engine = _heads_up_showdown(
        make_config(2),
        hero=("2c", "3d"),
        villain=("9c", "9d"),
        board=("As", "Ks", "Qs", "Js", "Ts"),
    )
    assert engine.state.result is not None
    assert engine.state.result.status == "split"
    assert engine.state.result.received["hero"] == 10
    assert engine.state.result.received["p2"] == 10


def test_mucked_hand_concedes_without_requiring_unknown_cards(
    make_config: Callable[..., SessionCreate],
) -> None:
    engine = _checkdown_to_showdown(make_config(2), ("As", "Ad"))
    engine.settle_showdown(ShowdownRequest(mucked_player_ids=["p2"]))
    assert engine.state.result is not None
    assert engine.state.result.winners == ["hero"]
    assert engine.state.result.received["hero"] == 20


def test_three_all_in_levels_create_multiple_side_pots_and_refund() -> None:
    players = [
        PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=50),
        PlayerConfig(id="p2", name="P2", seat=2, stack=100),
        PlayerConfig(id="p3", name="P3", seat=3, stack=200),
        PlayerConfig(id="p4", name="P4", seat=4, stack=300),
    ]
    config = SessionCreate(
        players=players,
        small_blind=5,
        big_blind=10,
        button_player_id="p2",
        small_blind_player_id="p3",
        big_blind_player_id="p4",
    )
    engine = HoldemEngine(config)
    for _ in range(3):
        engine.take_action(ActionRequest(action=ActionKind.ALL_IN))
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    engine.set_card("hero_1", "As")
    engine.set_card("hero_2", "Ad")
    _fill_runout(engine)
    assert engine.state.status == HandStatus.SHOWDOWN
    assert [pot.amount for pot in engine.state.pots] == [200, 150, 200]
    assert [pot.eligible_player_ids for pot in engine.state.pots] == [
        ["hero", "p2", "p3", "p4"],
        ["p2", "p3", "p4"],
        ["p3", "p4"],
    ]
    engine.settle_showdown(ShowdownRequest(manual_winners={0: ["hero"], 1: ["p2"], 2: ["p3"]}))
    result = engine.state.result
    assert result is not None
    assert result.resolution_method == "manual_assignment"
    assert result.refunds == {}
    assert sum(player.stack for player in engine.state.players) == 650
    assert result.net_results == {"hero": 150, "p2": 50, "p3": 0, "p4": -200}


def test_folded_contributor_is_not_eligible() -> None:
    players = [
        PlayerState(
            id="hero",
            name="Ryanchl",
            seat=1,
            stack=50,
            starting_stack=100,
            status=PlayerStatus.ACTIVE,
            total_contribution=50,
        ),
        PlayerState(
            id="folded",
            name="Fold",
            seat=2,
            stack=50,
            starting_stack=100,
            status=PlayerStatus.FOLDED,
            total_contribution=50,
        ),
        PlayerState(
            id="allin",
            name="All",
            seat=3,
            stack=0,
            starting_stack=20,
            status=PlayerStatus.ALL_IN,
            total_contribution=20,
        ),
    ]
    construction = build_pots(players)
    assert construction.pots[0].amount == 60
    assert construction.pots[0].eligible_player_ids == ["hero", "allin"]
    assert construction.pots[1].amount == 60
    assert construction.pots[1].eligible_player_ids == ["hero"]


def test_unknown_cards_require_manual_winner(make_config: Callable[..., SessionCreate]) -> None:
    engine = _checkdown_to_showdown(make_config(2), ("As", "Ad"))
    with pytest.raises(PokerRuleError, match="attribution manuelle"):
        engine.settle_showdown(ShowdownRequest())
    engine.settle_showdown(ShowdownRequest(manual_winners={0: ["hero"]}))
    assert engine.state.result is not None
    assert engine.state.result.status == "incomplete"
    assert engine.state.result.cards_complete is False


def test_duplicate_manual_winner_is_rejected(make_config: Callable[..., SessionCreate]) -> None:
    engine = _checkdown_to_showdown(make_config(2), ("As", "Ad"))
    with pytest.raises(PokerRuleError, match="plusieurs fois"):
        engine.settle_showdown(ShowdownRequest(manual_winners={0: ["hero", "hero"]}))


def test_revealed_card_duplicate_is_rejected(make_config: Callable[..., SessionCreate]) -> None:
    engine = _checkdown_to_showdown(make_config(2), ("As", "Ad"))
    with pytest.raises(PokerRuleError, match="plusieurs fois"):
        engine.settle_showdown(ShowdownRequest(revealed_hands={"p2": ["As", "Kh"]}))


def test_short_call_refund_is_retained_in_result() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=30),
            PlayerConfig(id="p2", name="P2", seat=2, stack=100),
        ],
        small_blind=5,
        big_blind=10,
        button_player_id="hero",
        small_blind_player_id="hero",
        big_blind_player_id="p2",
    )
    engine = HoldemEngine(config)
    engine.set_card("hero_1", "As")
    engine.set_card("hero_2", "Ad")
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    engine.take_action(ActionRequest(action=ActionKind.CHECK))
    for slot, card in zip(("flop_1", "flop_2", "flop_3"), ("2s", "3h", "4d"), strict=True):
        engine.set_card(slot, card)
    engine.take_action(ActionRequest(action=ActionKind.BET, amount=30))
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    engine.set_card("turn", "5c")
    engine.set_card("river", "9s")
    engine.settle_showdown(ShowdownRequest(revealed_hands={"p2": ["Kh", "Kd"]}))
    assert engine.state.result is not None
    assert engine.state.result.refunds["p2"] == 10


def _heads_up_showdown(
    config: SessionCreate,
    *,
    hero: tuple[str, str],
    villain: tuple[str, str],
    board: tuple[str, str, str, str, str] = ("2s", "3h", "7d", "9c", "Js"),
) -> HoldemEngine:
    engine = _checkdown_to_showdown(config, hero, board)
    engine.settle_showdown(ShowdownRequest(revealed_hands={"p2": list(villain)}))
    return engine


def _checkdown_to_showdown(
    config: SessionCreate,
    hero: tuple[str, str],
    board: tuple[str, str, str, str, str] = ("2s", "3h", "7d", "9c", "Js"),
) -> HoldemEngine:
    engine = HoldemEngine(config)
    engine.set_card("hero_1", hero[0])
    engine.set_card("hero_2", hero[1])
    while engine.state.status == HandStatus.ACTIVE:
        call = next(item for item in engine.state.legal_actions if item.action == ActionKind.CALL)
        engine.take_action(
            ActionRequest(action=ActionKind.CALL if call.enabled else ActionKind.CHECK)
        )
    for slot, card in zip(("flop_1", "flop_2", "flop_3"), board[:3], strict=True):
        engine.set_card(slot, card)
    for _ in range(2):
        engine.take_action(ActionRequest(action=ActionKind.CHECK))
    engine.set_card("turn", board[3])
    for _ in range(2):
        engine.take_action(ActionRequest(action=ActionKind.CHECK))
    engine.set_card("river", board[4])
    for _ in range(2):
        engine.take_action(ActionRequest(action=ActionKind.CHECK))
    return engine


def _fill_runout(engine: HoldemEngine) -> None:
    for slot, card in zip(
        ("flop_1", "flop_2", "flop_3", "turn", "river"),
        ("2s", "3h", "4d", "5c", "9s"),
        strict=True,
    ):
        engine.set_card(slot, card)
