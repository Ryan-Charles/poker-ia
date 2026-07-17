from __future__ import annotations

from collections.abc import Callable

import pytest

from app.engine.holdem import HoldemEngine, PokerRuleError
from app.engine.session import PokerSession
from app.models import (
    ActionKind,
    ActionRequest,
    CardRequest,
    HandStatus,
    InitialProfile,
    PlayerPatch,
    PlayerReplace,
    PlayerStatus,
    SessionCreate,
)


def test_restart_hand_matches_freshly_constructed_engine(
    make_config: Callable[..., SessionCreate],
) -> None:
    config = make_config(3)
    fresh = HoldemEngine(
        config,
        hand_number=1,
        hand_id="fixed-hand-id",
        button_player_id=config.button_player_id,
        players=config.players,
    )
    engine = HoldemEngine(
        config,
        hand_number=1,
        hand_id="fixed-hand-id",
        button_player_id=config.button_player_id,
        players=config.players,
    )
    engine.take_action(ActionRequest(action=ActionKind.CALL))
    engine.take_action(ActionRequest(action=ActionKind.RAISE, amount=30))
    engine.set_card("hero_1", "As")
    engine.set_card("hero_2", "Kd")
    engine.restart_hand()
    assert engine.state.model_dump(mode="json", exclude={"events"}) == fresh.state.model_dump(
        mode="json", exclude={"events"}
    )
    assert len(engine.events) == engine.forced_count
    assert engine.cursor == engine.forced_count
    assert engine.state.can_undo is False
    assert engine.state.can_redo is False


def test_restart_hand_resets_session_state_mid_hand(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    hand_id = session.engine.state.id
    session.set_card(CardRequest(slot="hero_1", card="As"))
    session.set_card(CardRequest(slot="hero_2", card="Kd"))
    session.generate_advice(trials=100, seed=5)
    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.RAISE, amount=30))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    assert session.opponents["p2"].hands_observed == 1
    assert len(session.advice_history) == 1

    session.restart_hand()

    assert session.engine.state.id == hand_id
    assert session.engine.state.number == 1
    assert session.engine.state.status == HandStatus.ACTIVE
    assert session.engine.state.board == []
    assert session.engine.state.hero_cards == []
    assert session.engine.state.actor_id == "hero"
    assert session.engine.state.pot == 15
    players = {player.id: player for player in session.engine.state.players}
    assert players["hero"].stack == 1_000
    assert players["hero"].total_contribution == 0
    assert players["p2"].stack == 995
    assert players["p2"].total_contribution == 5
    assert players["p3"].stack == 990
    assert players["p3"].total_contribution == 10
    assert session.advice_history == []
    assert session.decision_snapshots == {}
    assert session.current_advice is None
    assert session.opponents["p2"].hands_observed == 0


def test_restart_hand_after_completion_clears_summary_and_reopens_hand(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(2))
    session.take_action(ActionRequest(action=ActionKind.FOLD))
    assert session.engine.state.status == HandStatus.COMPLETE
    assert len(session.hand_summaries) == 1
    assert session.cumulative_hero_result != 0

    session.restart_hand()

    assert session.engine.state.status != HandStatus.COMPLETE
    assert session.hand_summaries == []
    assert session.cumulative_hero_result == 0
    assert session.engine.state.number == 1
    hero = next(player for player in session.engine.state.players if player.id == "hero")
    assert hero.status == PlayerStatus.ACTIVE
    assert hero.stack == 995
    assert session.engine.state.actor_id == "hero"


def test_restart_hand_then_replay_completes_normally(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(2))
    session.take_action(ActionRequest(action=ActionKind.FOLD))
    assert session.engine.state.status == HandStatus.COMPLETE

    session.restart_hand()
    assert session.engine.state.status == HandStatus.ACTIVE

    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.CHECK))
    assert session.engine.state.status == HandStatus.AWAITING_CARDS
    for slot, card in zip(("flop_1", "flop_2", "flop_3"), ("2s", "3h", "4d"), strict=True):
        session.set_card(CardRequest(slot=slot, card=card))
    assert session.engine.state.status == HandStatus.ACTIVE
    assert session.engine.state.actor_id is not None


def test_replace_player_resets_opponent_model_and_updates_name(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    assert session.opponents["p2"].hands_observed == 1

    session.replace_player(
        "p2", PlayerReplace(name="Nouveau Joueur", initial_profile=InitialProfile.LAG)
    )

    assert session.opponents["p2"].hands_observed == 0
    assert session.opponents["p2"].name == "Nouveau Joueur"
    assert session.opponents["p2"].initial_profile == InitialProfile.LAG
    assert session.hand_opponent_baselines["p2"].hands_observed == 0
    assert session.hand_opponent_baselines["p2"].name == "Nouveau Joueur"
    state = session.state()
    player = next(item for item in state.hand.players if item.id == "p2")
    assert player.name == "Nouveau Joueur"


def test_replace_player_refuses_hero(make_config: Callable[..., SessionCreate]) -> None:
    session = PokerSession(make_config(3))
    with pytest.raises(PokerRuleError, match="principal"):
        session.replace_player("hero", PlayerReplace(name="Quelqu'un d'autre"))


def test_replace_player_refuses_duplicate_name(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    with pytest.raises(PokerRuleError, match="déjà utilisé"):
        session.replace_player("p2", PlayerReplace(name="Joueur 3"))


def test_replace_player_refuses_empty_name(make_config: Callable[..., SessionCreate]) -> None:
    session = PokerSession(make_config(3))
    with pytest.raises(PokerRuleError, match="vide"):
        session.replace_player("p2", PlayerReplace(name="   "))


def test_replace_player_refuses_stack_below_committed_chips(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.RAISE, amount=50))
    with pytest.raises(PokerRuleError, match="tapis"):
        session.replace_player("p2", PlayerReplace(name="Nouveau", stack=40))


def test_replace_player_mid_hand_preserves_committed_chips(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.RAISE, amount=50))
    before = next(item for item in session.engine.state.players if item.id == "p2")
    contribution_before = before.total_contribution
    stack_before = before.stack
    status_before = before.status

    session.replace_player("p2", PlayerReplace(name="Nouveau Joueur"))

    after = next(item for item in session.engine.state.players if item.id == "p2")
    assert after.total_contribution == contribution_before
    assert after.stack == stack_before
    assert after.status == status_before
    displayed = next(item for item in session.state().hand.players if item.id == "p2")
    assert displayed.name == "Nouveau Joueur"


def test_stack_patch_is_immediate_after_actions_and_survives_restore(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    session.take_action(ActionRequest(action=ActionKind.CALL))

    session.patch_player("p2", PlayerPatch(stack=777))

    adjusted = next(player for player in session.engine.state.players if player.id == "p2")
    assert adjusted.stack == 777
    assert next(player for player in session.state().hand.players if player.id == "p2").stack == 777

    session.take_action(ActionRequest(action=ActionKind.CALL))
    after_action = next(player for player in session.engine.state.players if player.id == "p2")
    assert after_action.stack < 777
    restored = PokerSession.restore(session.export())
    restored_player = next(player for player in restored.engine.state.players if player.id == "p2")
    assert restored_player.stack == after_action.stack


def test_remove_then_seat_player_joins_on_next_hand(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))

    session.remove_player("p2")
    assert session.player_overrides["p2"]["status"] == PlayerStatus.ABSENT

    session.seat_player("p2", PlayerReplace(name="Jordan", stack=800))
    assert session.player_overrides["p2"]["pending_join"] is True
    assert session.player_overrides["p2"]["status"] == PlayerStatus.ACTIVE

    session.take_action(ActionRequest(action=ActionKind.FOLD))
    assert session.engine.state.status == HandStatus.COMPLETE

    session.next_hand()
    joined = next(player for player in session.engine.state.players if player.id == "p2")
    assert joined.name == "Jordan"
    assert joined.status in {PlayerStatus.ACTIVE, PlayerStatus.ALL_IN}
    assert joined.stack > 0
    assert session.player_overrides == {}
