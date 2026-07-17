from __future__ import annotations

from collections.abc import Callable

import pytest

from app.engine.holdem import HoldemEngine, PokerRuleError
from app.models import (
    ActionKind,
    ActionRequest,
    AnteType,
    HandStatus,
    PlayerConfig,
    SessionCreate,
    Street,
)


@pytest.mark.parametrize("player_count", range(2, 9))
def test_tables_two_to_eight_have_correct_preflop_actor(
    player_count: int, make_config: Callable[..., SessionCreate]
) -> None:
    engine = HoldemEngine(make_config(player_count))
    assert len(engine.state.players) == player_count
    assert engine.state.actor_id == "hero"
    assert engine.state.pot == 15
    assert engine.state.current_bet == 10


def test_heads_up_button_is_small_blind_and_acts_first(
    make_config: Callable[..., SessionCreate],
) -> None:
    engine = HoldemEngine(make_config(2))
    assert engine.state.button_player_id == "hero"
    assert engine.state.small_blind_player_id == "hero"
    assert engine.state.big_blind_player_id == "p2"
    assert engine.state.actor_id == "hero"


def test_invalid_heads_up_blinds_are_rejected() -> None:
    with pytest.raises(ValueError, match="heads-up"):
        SessionCreate(
            players=[
                PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=100),
                PlayerConfig(id="v", name="V", seat=2, stack=100),
            ],
            small_blind=5,
            big_blind=10,
            button_player_id="hero",
            small_blind_player_id="v",
            big_blind_player_id="hero",
        )


def test_classic_antes_are_posted_by_every_player(
    make_config: Callable[..., SessionCreate],
) -> None:
    engine = HoldemEngine(make_config(4, ante=2, ante_type=AnteType.CLASSIC))
    assert engine.state.pot == 23
    assert all(player.total_contribution >= 2 for player in engine.state.players)


def test_big_blind_ante_is_dead_money_not_refunded(
    make_config: Callable[..., SessionCreate],
) -> None:
    engine = HoldemEngine(make_config(2, ante=10, ante_type=AnteType.BIG_BLIND))
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    engine.take_action(ActionRequest(action=ActionKind.CHECK))
    assert engine.state.pot == 30
    assert [pot.amount for pot in engine.state.pots] == [30]


def test_big_blind_is_posted_before_short_stack_bba() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=100),
            PlayerConfig(id="v", name="V", seat=2, stack=15),
        ],
        small_blind=5,
        big_blind=10,
        ante=10,
        ante_type=AnteType.BIG_BLIND,
        button_player_id="hero",
        small_blind_player_id="hero",
        big_blind_player_id="v",
    )
    engine = HoldemEngine(config)
    villain = next(player for player in engine.state.players if player.id == "v")
    assert villain.street_contribution == 10
    assert villain.dead_money_contribution == 5


def test_call_check_advances_to_flop_request(make_config: Callable[..., SessionCreate]) -> None:
    engine = HoldemEngine(make_config(2))
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    engine.take_action(ActionRequest(action=ActionKind.CHECK))
    assert engine.state.street == Street.FLOP
    assert engine.state.status == HandStatus.AWAITING_CARDS
    assert engine.state.awaiting_slots == ["flop_1", "flop_2", "flop_3"]


def test_everyone_folding_awards_and_refunds_uncalled_raise(
    make_config: Callable[..., SessionCreate],
) -> None:
    engine = HoldemEngine(make_config(3))
    engine.take_action(ActionRequest(action=ActionKind.RAISE, amount=40))
    engine.take_action(ActionRequest(action=ActionKind.FOLD))
    engine.take_action(ActionRequest(action=ActionKind.FOLD))
    assert engine.state.status == HandStatus.COMPLETE
    assert engine.state.result is not None
    assert engine.state.result.status == "won_without_showdown"
    assert engine.state.result.refunds["hero"] == 30
    assert engine.state.result.net_results["hero"] == 15


def test_opening_bet_sets_minimum_raise_to_twice_bet(
    make_config: Callable[..., SessionCreate],
) -> None:
    engine = _to_flop(make_config(2))
    engine.take_action(ActionRequest(action=ActionKind.BET, amount=30))
    raise_action = _legal(engine, ActionKind.RAISE)
    assert raise_action.min_total == 60
    with pytest.raises(PokerRuleError):
        engine.take_action(ActionRequest(action=ActionKind.RAISE, amount=50))


def test_short_big_blind_requires_nominal_call_and_full_raise() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=100),
            PlayerConfig(id="v", name="V", seat=2, stack=3),
        ],
        small_blind=5,
        big_blind=10,
        button_player_id="hero",
        small_blind_player_id="hero",
        big_blind_player_id="v",
    )
    engine = HoldemEngine(config)
    assert engine.state.current_bet == 5
    assert _legal(engine, ActionKind.CALL).to_call == 5
    raise_action = _legal(engine, ActionKind.RAISE)
    assert raise_action.enabled is False
    assert raise_action.reason == "Aucun adversaire ne peut suivre une relance"
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    action_event = next(event for event in engine.state.events if event.type.value == "action")
    assert action_event.total == 10
    assert action_event.payload["resolved_action"] == "call"


def test_short_big_blind_keeps_nominal_full_raise_with_two_actionable_players() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=100),
            PlayerConfig(id="sb", name="SB", seat=2, stack=100),
            PlayerConfig(id="bb", name="BB", seat=3, stack=3),
        ],
        small_blind=5,
        big_blind=10,
        button_player_id="hero",
        small_blind_player_id="sb",
        big_blind_player_id="bb",
    )
    engine = HoldemEngine(config)
    assert _legal(engine, ActionKind.CALL).to_call == 10
    assert _legal(engine, ActionKind.RAISE).min_total == 20


def test_forced_all_ins_immediately_enter_runout(make_config: Callable[..., SessionCreate]) -> None:
    engine = HoldemEngine(make_config(2, stacks=[5, 10]))
    assert engine.state.runout_mode is True
    assert engine.state.status == HandStatus.AWAITING_CARDS
    assert engine.state.awaiting_slots == ["flop_1", "flop_2", "flop_3"]


def test_lone_big_blind_does_not_receive_pointless_action() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=5),
            PlayerConfig(id="v", name="V", seat=2, stack=100),
        ],
        small_blind=5,
        big_blind=10,
        button_player_id="hero",
        small_blind_player_id="hero",
        big_blind_player_id="v",
    )
    engine = HoldemEngine(config)
    assert engine.state.actor_id is None
    assert engine.state.runout_mode is True
    assert engine.state.refunds["v"] == 5
    assert engine.state.status == HandStatus.AWAITING_CARDS


def test_incoherent_three_player_blind_order_is_rejected() -> None:
    with pytest.raises(ValueError, match="ordre des blindes"):
        SessionCreate(
            players=[
                PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=100),
                PlayerConfig(id="p2", name="P2", seat=2, stack=100),
                PlayerConfig(id="p3", name="P3", seat=3, stack=100),
            ],
            small_blind=5,
            big_blind=10,
            button_player_id="hero",
            small_blind_player_id="p3",
            big_blind_player_id="p2",
        )


def test_single_short_all_in_does_not_reopen_betting() -> None:
    players = [
        PlayerConfig(id="sb", name="SB", seat=1, stack=125),
        PlayerConfig(id="bb", name="BB", seat=2, stack=500),
        PlayerConfig(id="hero", name="Ryanchl", seat=3, stack=500),
        PlayerConfig(id="btn", name="BTN", seat=4, stack=500),
    ]
    engine = HoldemEngine(_four_player_config(players))
    engine.take_action(ActionRequest(action=ActionKind.RAISE, amount=100))
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    engine.take_action(ActionRequest(action=ActionKind.ALL_IN))
    engine.take_action(ActionRequest(action=ActionKind.FOLD))
    assert engine.state.actor_id == "hero"
    assert _legal(engine, ActionKind.RAISE).enabled is False
    assert _legal(engine, ActionKind.ALL_IN).enabled is False


def test_cumulative_short_all_ins_reopen_betting() -> None:
    players = [
        PlayerConfig(id="sb", name="SB", seat=1, stack=125),
        PlayerConfig(id="bb", name="BB", seat=2, stack=200),
        PlayerConfig(id="hero", name="Ryanchl", seat=3, stack=500),
        PlayerConfig(id="btn", name="BTN", seat=4, stack=500),
    ]
    engine = HoldemEngine(_four_player_config(players))
    engine.take_action(ActionRequest(action=ActionKind.RAISE, amount=100))
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    engine.take_action(ActionRequest(action=ActionKind.ALL_IN))
    engine.take_action(ActionRequest(action=ActionKind.ALL_IN))
    assert engine.state.actor_id == "hero"
    assert _legal(engine, ActionKind.RAISE).enabled is True
    assert _legal(engine, ActionKind.RAISE).min_total == 290


def test_short_open_after_check_does_not_reopen_to_checker() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="p3", name="P3", seat=1, stack=100),
            PlayerConfig(id="p4", name="P4", seat=2, stack=15),
            PlayerConfig(id="hero", name="Ryanchl", seat=3, stack=100),
            PlayerConfig(id="btn", name="BTN", seat=4, stack=100),
        ],
        small_blind=5,
        big_blind=10,
        button_player_id="btn",
        small_blind_player_id="p3",
        big_blind_player_id="p4",
    )
    engine = HoldemEngine(config)
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    engine.take_action(ActionRequest(action=ActionKind.FOLD))
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    engine.take_action(ActionRequest(action=ActionKind.CHECK))
    for slot, card in zip(("flop_1", "flop_2", "flop_3"), ("2s", "3h", "4d"), strict=True):
        engine.set_card(slot, card)
    assert engine.state.actor_id == "p3"
    engine.take_action(ActionRequest(action=ActionKind.CHECK))
    assert engine.state.actor_id == "p4"
    engine.take_action(ActionRequest(action=ActionKind.ALL_IN))
    assert engine.state.actor_id == "hero"
    assert _legal(engine, ActionKind.RAISE).enabled is True
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    assert engine.state.actor_id == "p3"
    assert _legal(engine, ActionKind.RAISE).enabled is False


def test_undo_redo_and_restore_are_event_sourced(make_config: Callable[..., SessionCreate]) -> None:
    engine = HoldemEngine(make_config(3))
    initial_actor = engine.state.actor_id
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    after_call = engine.state.model_dump(mode="json", exclude={"can_undo", "can_redo"})
    engine.undo()
    assert engine.state.actor_id == initial_actor
    engine.redo()
    assert engine.state.actor_id != initial_actor
    restored = HoldemEngine.restore(engine.export())
    assert restored.state.model_dump(mode="json", exclude={"can_undo", "can_redo"}) == after_call


def _to_flop(config: SessionCreate) -> HoldemEngine:
    engine = HoldemEngine(config)
    while engine.state.status == HandStatus.ACTIVE:
        call = _legal(engine, ActionKind.CALL)
        action = ActionKind.CALL if call.enabled else ActionKind.CHECK
        engine.take_action(ActionRequest(action=action))
    for slot, card in zip(("flop_1", "flop_2", "flop_3"), ("2s", "3h", "4d"), strict=True):
        engine.set_card(slot, card)
    return engine


def _legal(engine: HoldemEngine, action: ActionKind):
    return next(item for item in engine.state.legal_actions if item.action == action)


def _four_player_config(players: list[PlayerConfig]) -> SessionCreate:
    return SessionCreate(
        players=players,
        small_blind=5,
        big_blind=10,
        button_player_id="btn",
        small_blind_player_id="sb",
        big_blind_player_id="bb",
    )
