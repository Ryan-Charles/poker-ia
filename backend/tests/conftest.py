from __future__ import annotations

from collections.abc import Callable

import pytest

from app.models import AnteType, PlayerConfig, SessionCreate


@pytest.fixture
def make_config() -> Callable[..., SessionCreate]:
    def factory(
        player_count: int = 3,
        *,
        stacks: list[int] | None = None,
        ante: int = 0,
        ante_type: AnteType = AnteType.NONE,
    ) -> SessionCreate:
        values = stacks or [1_000] * player_count
        players = [
            PlayerConfig(
                id="hero" if index == 0 else f"p{index + 1}",
                name="Ryanchl" if index == 0 else f"Joueur {index + 1}",
                seat=index + 1,
                stack=values[index],
            )
            for index in range(player_count)
        ]
        if player_count == 2:
            button, small, big = "hero", "hero", "p2"
        else:
            button = "hero" if player_count == 3 else f"p{player_count - 2}"
            small = f"p{player_count - 1}"
            big = f"p{player_count}"
        return SessionCreate(
            players=players,
            small_blind=5,
            big_blind=10,
            ante=ante,
            ante_type=ante_type,
            button_player_id=button,
            small_blind_player_id=small,
            big_blind_player_id=big,
        )

    return factory
