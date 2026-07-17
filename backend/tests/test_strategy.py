from __future__ import annotations

from collections.abc import Callable

import pytest

from app.engine.holdem import HoldemEngine
from app.models import ActionKind, AnalysisLevel, SessionCreate
from app.opponents.model import OpponentModel
from app.strategy.advisor import StrategyAdvisor, pot_odds, stack_to_pot_ratio
from app.strategy.equity import RangeParameters, combo_weight, estimate_equity
from app.strategy.preflop import PREFLOP_TABLE_VERSION, chart_decision, interpolate_threshold


def test_pot_odds_and_spr() -> None:
    assert pot_odds(100, 25) == pytest.approx(0.20)
    assert pot_odds(100, 0) == 0
    assert stack_to_pot_ratio(250, 100) == 2.5
    assert stack_to_pot_ratio(250, 0) == float("inf")


def test_preflop_table_version_interpolation_and_strength() -> None:
    middle = interpolate_threshold("BTN", 30)
    assert 0.53 < middle < 0.55
    premium = chart_decision(
        ["As", "Ad"], position="UTG", stack_bb=100, facing_raise=True, raise_count=1
    )
    trash = chart_decision(
        ["7c", "2d"], position="UTG", stack_bb=100, facing_raise=True, raise_count=1
    )
    assert premium.table_version == PREFLOP_TABLE_VERSION
    assert premium.action == ActionKind.RAISE
    assert trash.action == ActionKind.FOLD


def test_range_weight_responds_to_tightness() -> None:
    premium = ("As", "Ad")
    weak = ("7c", "2d")
    tight = RangeParameters(vpip=0.15, preflop_raise=True)
    loose = RangeParameters(vpip=0.60)
    assert combo_weight(premium, tight) / combo_weight(weak, tight) > combo_weight(
        premium, loose
    ) / combo_weight(weak, loose)


def test_monte_carlo_seed_is_reproducible_and_does_not_expose_samples() -> None:
    kwargs = {
        "hero_cards": ["As", "Ad"],
        "board": ["2s", "3h", "7d"],
        "opponent_ranges": [RangeParameters(vpip=0.25)],
        "trials": 200,
        "seed": 42,
    }
    first = estimate_equity(**kwargs)
    second = estimate_equity(**kwargs)
    assert first == second
    assert not hasattr(first, "opponent_cards")
    assert first.equity > 0.5


def test_multiway_equity_is_lower_than_heads_up() -> None:
    hero = ["As", "Ad"]
    board = ["2s", "3h", "7d"]
    heads_up = estimate_equity(hero, board, [RangeParameters()], trials=250, seed=5).equity
    multiway = estimate_equity(
        hero, board, [RangeParameters(), RangeParameters()], trials=250, seed=5
    ).equity
    assert multiway < heads_up


def test_advisor_returns_only_legal_actions_and_explicit_estimation(
    make_config: Callable[..., SessionCreate],
) -> None:
    config = make_config(3)
    engine = HoldemEngine(config)
    engine.set_card("hero_1", "As")
    engine.set_card("hero_2", "Kd")
    opponents = {
        player.id: OpponentModel(player_id=player.id, name=player.name)
        for player in config.players
        if player.id != "hero"
    }
    advice = StrategyAdvisor().advise(
        session_id="session",
        config=config,
        state=engine.state,
        opponents=opponents,
        level=AnalysisLevel.FAST,
        trials=150,
        seed=99,
    )
    legal = {item.action for item in engine.state.legal_actions if item.enabled}
    assert {item.action for item in advice.alternatives} <= legal
    assert advice.primary_action in legal
    assert advice.precision == "monte_carlo_estimate"
    assert PREFLOP_TABLE_VERSION in advice.source
    assert "estimation" in advice.explanation.lower()
    assert sum(item.frequency for item in advice.alternatives) == pytest.approx(1.0)


def test_exploit_guard_is_small_with_few_observations(
    make_config: Callable[..., SessionCreate],
) -> None:
    config = make_config(3)
    engine = HoldemEngine(config)
    engine.set_card("hero_1", "As")
    engine.set_card("hero_2", "Kd")
    opponents = {
        player.id: OpponentModel(player_id=player.id, name=player.name)
        for player in config.players
        if player.id != "hero"
    }
    advice = StrategyAdvisor().advise(
        session_id="session",
        config=config,
        state=engine.state,
        opponents=opponents,
        trials=120,
        seed=1,
    )
    for item in advice.alternatives:
        assert item.guarded_ev == pytest.approx(item.balanced_ev)


def test_deep_advice_reports_local_regret_matching_source(
    make_config: Callable[..., SessionCreate],
) -> None:
    config = make_config(2)
    engine = HoldemEngine(config)
    engine.set_card("hero_1", "As")
    engine.set_card("hero_2", "Kd")
    opponents = {"p2": OpponentModel(player_id="p2", name="Joueur 2")}
    advice = StrategyAdvisor().advise(
        session_id="session",
        config=config,
        state=engine.state,
        opponents=opponents,
        level=AnalysisLevel.DEEP,
        trials=100,
        seed=3,
    )
    assert "regret_matching_local" in advice.source
    assert sum(item.frequency for item in advice.alternatives) == pytest.approx(1.0)


def test_strategy_cache_is_bounded_and_returns_fresh_decision_records(
    make_config: Callable[..., SessionCreate],
) -> None:
    config = make_config(2)
    engine = HoldemEngine(config)
    engine.set_card("hero_1", "As")
    engine.set_card("hero_2", "Kd")
    opponents = {"p2": OpponentModel(player_id="p2", name="Joueur 2")}
    advisor = StrategyAdvisor(cache_size=2)
    arguments = {
        "session_id": "session",
        "config": config,
        "state": engine.state,
        "opponents": opponents,
        "trials": 100,
    }
    first = advisor.advise(**arguments, seed=11)
    first.actual_action = ActionKind.FOLD
    second = advisor.advise(**arguments, seed=11)
    assert advisor.cache_hits == 1
    assert second.id != first.id
    assert second.equity == first.equity
    assert second.actual_action is None
    advisor.advise(**arguments, seed=12)
    advisor.advise(**arguments, seed=13)
    assert advisor.cache_entries == 2
