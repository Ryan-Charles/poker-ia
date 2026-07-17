from __future__ import annotations

from collections.abc import Callable

import pytest

from app.engine.holdem import HoldemEngine, PokerRuleError
from app.engine.session import PokerSession
from app.models import (
    ActionKind,
    ActionRequest,
    CardRequest,
    InitialProfile,
    OpponentPatch,
    PlayerConfig,
    SessionCreate,
    Street,
)
from app.opponents.model import BayesianStat, OpponentModel
from app.presentation import decision_detail_view, history_decision_view


def test_neutral_bayesian_prior_and_interval() -> None:
    stat = BayesianStat(prior_success=5, prior_failure=15)
    assert stat.mean == pytest.approx(0.25)
    low, high = stat.credible_interval
    assert 0 <= low < stat.mean < high <= 1
    assert stat.confidence == 0


def test_vpip_pfr_and_position_statistics() -> None:
    model = OpponentModel(player_id="v", name="V")
    model.observe_action(
        hand_id="h1",
        street=Street.PREFLOP,
        action=ActionKind.RAISE,
        position="CO",
        facing_raise=False,
    )
    assert model.hands_observed == 1
    assert model.stats["vpip"].successes == 1
    assert model.stats["pfr"].successes == 1
    assert model.position_stats["CO"]["vpip"].successes == 1


def test_repeated_preflop_raises_identify_large_aggressive_profile() -> None:
    model = OpponentModel(player_id="v", name="V")
    for index in range(30):
        model.observe_action(
            hand_id=f"h{index}",
            street=Street.PREFLOP,
            action=ActionKind.RAISE,
            position="BTN",
        )
    assert model.stats["vpip"].mean > 0.35
    assert model.stats["pfr"].mean > 0.60
    assert model.estimated_profile == "large_agressif"


def test_three_bet_and_fold_to_cbet() -> None:
    model = OpponentModel(player_id="v", name="V")
    model.observe_action(
        hand_id="h1",
        street=Street.PREFLOP,
        action=ActionKind.RAISE,
        position="BTN",
        facing_raise=True,
        raise_count=1,
    )
    model.observe_action(
        hand_id="h1",
        street=Street.FLOP,
        action=ActionKind.FOLD,
        position="BTN",
        facing_cbet=True,
    )
    assert model.stats["three_bet"].successes == 1
    assert model.stats["fold_to_cbet"].successes == 1


def test_recent_weighting_detects_change_without_erasing_history() -> None:
    stat = BayesianStat()
    for _ in range(30):
        stat.observe(False)
    historical = stat.mean
    for _ in range(20):
        stat.observe(True)
    assert stat.recent_mean > historical
    assert stat.raw_opportunities == 50


@pytest.mark.parametrize(
    ("opportunities", "maximum"),
    [(5, 0.10), (20, 0.25), (60, 0.55), (150, 0.85)],
)
def test_adaptation_guard_by_sample_size(opportunities: int, maximum: float) -> None:
    model = OpponentModel(player_id="v", name="V")
    for index in range(opportunities):
        model.observe_action(
            hand_id=f"h{index}",
            street=Street.PREFLOP,
            action=ActionKind.CALL,
            position="BB",
        )
    assert model.confidence <= maximum


def test_revealed_bluff_only_updates_when_known() -> None:
    model = OpponentModel(player_id="v", name="V")
    before = model.stats["bluff_revealed"].raw_opportunities
    assert before == 0
    model.observe_showdown(won=False, bluff=True)
    assert model.observed_bluffs == 1
    assert model.stats["bluff_revealed"].successes == 1


def test_export_import_reset_and_merge() -> None:
    first = OpponentModel(player_id="v", name="V", initial_profile=InitialProfile.LAG)
    first.observe_action(
        hand_id="h1", street=Street.PREFLOP, action=ActionKind.RAISE, position="BTN"
    )
    restored = OpponentModel.model_validate_json(first.model_dump_json())
    assert restored.stats["pfr"].successes == 1
    second = OpponentModel(player_id="v2", name="V2")
    second.merge(first)
    assert second.hands_observed == 1
    reset = OpponentModel(player_id=first.player_id, name=first.name)
    assert reset.hands_observed == 0


def test_invalid_action_does_not_pollute_profile_and_undo_rolls_back(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    hero = session.engine.state.actor_id
    assert hero == "hero"
    session.take_action(ActionRequest(action=ActionKind.CALL))
    actor = session.engine.state.actor_id
    assert actor == "p2"
    before = session.opponents["p2"].stats["pfr"].raw_opportunities
    with pytest.raises(PokerRuleError):
        session.take_action(ActionRequest(action=ActionKind.RAISE, amount=11))
    assert session.opponents["p2"].stats["pfr"].raw_opportunities == before
    session.take_action(ActionRequest(action=ActionKind.CALL))
    assert session.opponents["p2"].hands_observed == 1
    session.undo()
    assert session.opponents["p2"].hands_observed == 0


def test_all_in_call_is_not_classified_as_preflop_raise() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=100),
            PlayerConfig(id="p2", name="P2", seat=2, stack=8),
            PlayerConfig(id="p3", name="P3", seat=3, stack=100),
        ],
        small_blind=5,
        big_blind=10,
        button_player_id="hero",
        small_blind_player_id="p2",
        big_blind_player_id="p3",
    )
    session = PokerSession(config)
    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.ALL_IN))
    model = session.opponents["p2"]
    assert model.stats["vpip"].successes == 1
    assert model.stats["pfr"].successes == 0


def test_all_in_call_does_not_increment_raise_count_for_next_three_bet() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=30),
            PlayerConfig(id="o", name="O", seat=2, stack=100),
            PlayerConfig(id="c", name="C", seat=3, stack=100),
            PlayerConfig(id="r", name="R", seat=4, stack=100),
        ],
        small_blind=5,
        big_blind=10,
        button_player_id="hero",
        small_blind_player_id="o",
        big_blind_player_id="c",
    )
    session = PokerSession(config)
    session.take_action(ActionRequest(action=ActionKind.RAISE, amount=30))
    session.take_action(ActionRequest(action=ActionKind.ALL_IN))
    session.take_action(ActionRequest(action=ActionKind.RAISE, amount=70))
    event = next(
        item
        for item in session.engine.state.events
        if item.actor_id == "o" and item.type.value == "action"
    )
    assert event.payload["raise_count"] == 1
    assert session.opponents["o"].stats["three_bet"].successes == 1
    assert session.opponents["o"].stats["four_bet"].raw_opportunities == 0


def test_limp_then_three_bet_promotes_single_pfr_observation(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.RAISE, amount=30))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.RAISE, amount=70))
    model = session.opponents["p2"]
    assert model.stats["pfr"].raw_opportunities == 1
    assert model.stats["pfr"].successes == 1
    assert model.stats["pfr"].failures == 0
    assert model.stats["three_bet"].successes == 1


def test_checked_flop_cbet_opportunity_is_recorded_as_failure(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.RAISE, amount=30))
    session.take_action(ActionRequest(action=ActionKind.FOLD))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    for slot, card in zip(("flop_1", "flop_2", "flop_3"), ("2s", "3h", "4d"), strict=True):
        session.set_card(CardRequest(slot=slot, card=card))
    assert session.engine.state.actor_id == "p2"
    session.take_action(ActionRequest(action=ActionKind.CHECK))
    cbet = session.opponents["p2"].stats["cbet_flop"]
    assert cbet.raw_opportunities == 1
    assert cbet.successes == 0
    assert cbet.failures == 1


def test_decision_snapshot_freezes_opponents_for_detail_and_expert_analysis(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    session.set_card(CardRequest(slot="hero_1", card="As"))
    session.set_card(CardRequest(slot="hero_2", card="Kd"))
    advice = session.generate_advice(trials=100, seed=21)
    detail_before = decision_detail_view(session, advice)
    replay_steps = detail_before["replay_steps"]
    assert replay_steps[0]["label"] == "Blindes et antes posées"
    assert replay_steps[-1]["known_cards"] == ["As", "Kd"]
    assert replay_steps[-1]["table_state"]["hand"]["active_player_id"] == "hero"
    assert replay_steps[-1]["advice"]["final"] == detail_before["final_advice"]
    assert all("revealed_hands" not in step["table_state"]["hand"] for step in replay_steps)
    expert_before = session.expert_analysis(advice.id, trials=100, seed=22)
    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    assert session.opponents["p2"].stats["vpip"].mean != detail_before["statistics_used"]["p2.vpip"]
    detail_after = decision_detail_view(session, advice)
    expert_after = session.expert_analysis(advice.id, trials=100, seed=22)
    assert detail_after["statistics_used"] == detail_before["statistics_used"]
    assert expert_after.equity == expert_before.equity
    assert expert_after.fold_equity == expert_before.fold_equity


def test_history_list_uses_frozen_light_context_without_replaying_engine(
    make_config: Callable[..., SessionCreate],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = PokerSession(make_config(3))
    session.set_card(CardRequest(slot="hero_1", card="As"))
    session.set_card(CardRequest(slot="hero_2", card="Kd"))
    advice = session.generate_advice(trials=100, seed=31)

    def forbidden_restore(_cls: type[HoldemEngine], _payload: dict[str, object]) -> None:
        raise AssertionError("La liste légère ne doit pas reconstruire le moteur")

    monkeypatch.setattr(HoldemEngine, "restore", classmethod(forbidden_restore))
    row = history_decision_view(session, advice)
    assert row["hero_cards"] == ["As", "Kd"]
    assert row["position"] == "BTN"
    assert row["hand_number"] == 1


def test_profile_changes_invalidate_current_advice(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    session.set_card(CardRequest(slot="hero_1", card="As"))
    session.set_card(CardRequest(slot="hero_2", card="Kd"))
    session.generate_advice(trials=100, seed=1)
    session.patch_opponent("p2", OpponentPatch(notes="Nouvelle lecture"))
    assert session.current_advice is None
    session.generate_advice(trials=100, seed=2)
    session.reset_opponent("p2")
    assert session.current_advice is None
    session.generate_advice(trials=100, seed=3)
    session.merge_opponents("p2", "p3")
    assert session.current_advice is None
    session.generate_advice(trials=100, seed=4)
    session.import_opponent(session.opponents["p2"])
    assert session.current_advice is None


def test_custom_opponent_patch_requires_description() -> None:
    with pytest.raises(ValueError, match="description"):
        OpponentPatch(initial_profile=InitialProfile.CUSTOM)
    patch = OpponentPatch(
        initial_profile=InitialProfile.CUSTOM,
        custom_profile="Serré hors position et très large au bouton.",
    )
    assert patch.custom_profile is not None


def test_fold_to_continuation_bet_is_recorded(make_config: Callable[..., SessionCreate]) -> None:
    session = PokerSession(make_config(3))
    session.take_action(ActionRequest(action=ActionKind.RAISE, amount=30))
    session.take_action(ActionRequest(action=ActionKind.CALL))
    session.take_action(ActionRequest(action=ActionKind.FOLD))
    for slot, card in zip(("flop_1", "flop_2", "flop_3"), ("2s", "3h", "4d"), strict=True):
        session.set_card(CardRequest(slot=slot, card=card))
    session.take_action(ActionRequest(action=ActionKind.CHECK))
    session.take_action(ActionRequest(action=ActionKind.BET, amount=20))
    session.take_action(ActionRequest(action=ActionKind.FOLD))
    assert session.opponents["p2"].stats["fold_to_cbet"].raw_opportunities == 1
    assert session.opponents["p2"].stats["fold_to_cbet"].successes == 1


def test_advice_actual_action_is_reconciled_after_branching(
    make_config: Callable[..., SessionCreate],
) -> None:
    session = PokerSession(make_config(3))
    session.set_card(CardRequest(slot="hero_1", card="As"))
    session.set_card(CardRequest(slot="hero_2", card="Kd"))
    advice = session.generate_advice(trials=100, seed=4)
    session.take_action(ActionRequest(action=ActionKind.CALL))
    assert advice.actual_action == ActionKind.CALL
    session.undo()
    assert advice.actual_action is None
    session.take_action(ActionRequest(action=ActionKind.FOLD))
    assert advice.actual_action == ActionKind.FOLD
