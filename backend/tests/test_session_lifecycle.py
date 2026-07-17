from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.engine.session import PokerSession
from app.models import (
    ActionKind,
    ActionRequest,
    AnteType,
    BlindLevel,
    GameMode,
    InitialProfile,
    PlayerConfig,
    SessionCreate,
)


def test_exact_tournament_blind_level_applies_on_next_hand() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=1_000),
            PlayerConfig(id="p2", name="P2", seat=2, stack=1_000),
            PlayerConfig(id="p3", name="P3", seat=3, stack=1_000),
        ],
        small_blind=5,
        big_blind=10,
        ante_type=AnteType.CLASSIC,
        mode=GameMode.TOURNAMENT,
        button_player_id="hero",
        small_blind_player_id="p2",
        big_blind_player_id="p3",
        blind_levels=[BlindLevel(after_hands=1, small_blind=10, big_blind=20, ante=2)],
    )
    session = PokerSession(config)
    session.take_action(ActionRequest(action=ActionKind.FOLD))
    session.take_action(ActionRequest(action=ActionKind.FOLD))
    session.next_hand()
    assert session.config.small_blind == 10
    assert session.config.big_blind == 20
    assert session.config.ante == 2
    assert session.engine.state.pot == 36


def test_time_based_tournament_level_is_supported() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=1_000),
            PlayerConfig(id="p2", name="P2", seat=2, stack=1_000),
        ],
        small_blind=5,
        big_blind=10,
        mode=GameMode.TOURNAMENT,
        button_player_id="hero",
        small_blind_player_id="hero",
        big_blind_player_id="p2",
        blind_levels=[BlindLevel(after_minutes=10, small_blind=15, big_blind=30, ante=0)],
    )
    session = PokerSession(config)
    session.created_at = datetime.now(UTC) - timedelta(minutes=11)
    session.take_action(ActionRequest(action=ActionKind.FOLD))
    session.next_hand()
    assert session.config.big_blind == 30


def test_custom_profile_round_trip_is_not_discarded() -> None:
    description = "Très large au bouton, mais prudent hors position."
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=100),
            PlayerConfig(
                id="p2",
                name="P2",
                seat=2,
                stack=100,
                initial_profile=InitialProfile.CUSTOM,
                custom_profile=description,
            ),
        ],
        small_blind=5,
        big_blind=10,
        button_player_id="hero",
        small_blind_player_id="hero",
        big_blind_player_id="p2",
    )
    session = PokerSession(config)
    restored = PokerSession.restore(session.export())
    assert restored.config.players[1].custom_profile == description
    assert restored.opponents["p2"].custom_profile == description


def test_absent_override_is_skipped_when_rotating_button() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=100),
            PlayerConfig(id="p2", name="P2", seat=2, stack=100),
            PlayerConfig(id="p3", name="P3", seat=3, stack=100),
        ],
        small_blind=5,
        big_blind=10,
        button_player_id="hero",
        small_blind_player_id="p2",
        big_blind_player_id="p3",
    )
    session = PokerSession(config)
    session.take_action(ActionRequest(action=ActionKind.FOLD))
    session.take_action(ActionRequest(action=ActionKind.FOLD))
    from app.models import PlayerPatch

    session.patch_player("p2", PlayerPatch(status="absent"))
    session.next_hand()
    assert session.engine.state.button_player_id == "p3"


def test_session_report_uses_received_chips_and_full_lost_pot_size() -> None:
    config = SessionCreate(
        players=[
            PlayerConfig(id="hero", name="Ryanchl", seat=1, stack=1_000),
            PlayerConfig(id="p2", name="P2", seat=2, stack=1_000),
        ],
        small_blind=5,
        big_blind=10,
        button_player_id="hero",
        small_blind_player_id="hero",
        big_blind_player_id="p2",
    )
    session = PokerSession(config)
    session.hand_summaries = [
        {
            "hand_id": "won",
            "status": "won",
            "hero_net": 100,
            "hero_received": 200,
            "total_pot": 200,
        },
        {
            "hand_id": "lost",
            "status": "lost",
            "hero_net": -100,
            "hero_received": 0,
            "total_pot": 200,
        },
    ]
    summary = session.session_summary()
    assert summary["biggest_pot_won"] == 200
    assert summary["biggest_pot_lost"] == 200
