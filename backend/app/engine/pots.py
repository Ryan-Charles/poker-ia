from __future__ import annotations

from dataclasses import dataclass

from app.models import PlayerState, PlayerStatus, PotView


@dataclass(frozen=True, slots=True)
class PotConstruction:
    pots: tuple[PotView, ...]
    refunds: dict[str, int]
    adjusted_contributions: dict[str, int]


def build_pots(players: list[PlayerState]) -> PotConstruction:
    contributions = {
        player.id: player.total_contribution - player.dead_money_contribution for player in players
    }
    dead_money = sum(player.dead_money_contribution for player in players)
    refunds: dict[str, int] = {}
    levels = sorted({amount for amount in contributions.values() if amount > 0})
    previous = 0
    pots: list[PotView] = []
    player_by_id = {player.id: player for player in players}
    for level in levels:
        contributors = [player_id for player_id, amount in contributions.items() if amount >= level]
        amount = (level - previous) * len(contributors)
        eligible = [
            player_id
            for player_id in contributors
            if player_by_id[player_id].status
            not in {PlayerStatus.FOLDED, PlayerStatus.ABSENT, PlayerStatus.ELIMINATED}
        ]
        if amount > 0:
            index = len(pots)
            pots.append(
                PotView(
                    index=index,
                    name="Pot principal" if index == 0 else f"Pot secondaire {index}",
                    amount=amount,
                    eligible_player_ids=eligible,
                )
            )
        previous = level
    if dead_money:
        if pots:
            pots[0] = pots[0].model_copy(update={"amount": pots[0].amount + dead_money})
        else:
            eligible = [
                player.id
                for player in players
                if player.status
                not in {PlayerStatus.FOLDED, PlayerStatus.ABSENT, PlayerStatus.ELIMINATED}
            ]
            pots.append(
                PotView(
                    index=0,
                    name="Pot principal",
                    amount=dead_money,
                    eligible_player_ids=eligible,
                )
            )
    return PotConstruction(tuple(pots), refunds, contributions)


def odd_chip_order(
    player_ids: list[str], players: list[PlayerState], button_player_id: str
) -> list[str]:
    seats = sorted(players, key=lambda player: player.seat)
    button_index = next(
        index for index, player in enumerate(seats) if player.id == button_player_id
    )
    clockwise = seats[button_index + 1 :] + seats[: button_index + 1]
    allowed = set(player_ids)
    return [player.id for player in clockwise if player.id in allowed]
