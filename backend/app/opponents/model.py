from __future__ import annotations

from datetime import UTC, datetime
from math import exp, sqrt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import ActionKind, InitialProfile, Street


class BayesianStat(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prior_success: float = 1.0
    prior_failure: float = 1.0
    successes: float = 0.0
    failures: float = 0.0
    raw_opportunities: int = 0
    recent_successes: float = 0.0
    recent_opportunities: float = 0.0

    def observe(self, success: bool, *, weight: float = 1.0, recent_decay: float = 0.94) -> None:
        self.successes += weight if success else 0.0
        self.failures += 0.0 if success else weight
        self.raw_opportunities += 1
        self.recent_successes = self.recent_successes * recent_decay + (weight if success else 0.0)
        self.recent_opportunities = self.recent_opportunities * recent_decay + weight

    @property
    def mean(self) -> float:
        alpha = self.prior_success + self.successes
        beta = self.prior_failure + self.failures
        return alpha / (alpha + beta)

    @property
    def recent_mean(self) -> float:
        if self.recent_opportunities <= 0:
            return self.mean
        raw = self.recent_successes / self.recent_opportunities
        confidence = min(1.0, self.recent_opportunities / 30.0)
        return self.mean * (1.0 - confidence) + raw * confidence

    @property
    def confidence(self) -> float:
        return 1.0 - exp(-self.raw_opportunities / 35.0)

    @property
    def credible_interval(self) -> tuple[float, float]:
        alpha = self.prior_success + self.successes
        beta = self.prior_failure + self.failures
        variance = alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1.0))
        half = 1.96 * sqrt(variance)
        return max(0.0, self.mean - half), min(1.0, self.mean + half)

    def merge(self, other: BayesianStat) -> None:
        self.successes += other.successes
        self.failures += other.failures
        self.raw_opportunities += other.raw_opportunities
        self.recent_successes = (self.recent_successes + other.recent_successes) / 2.0
        self.recent_opportunities = (self.recent_opportunities + other.recent_opportunities) / 2.0

    def promote_latest_failure(self) -> None:
        """Replace this hand's provisional failure with a success."""
        if self.failures <= 0:
            return
        self.failures -= 1.0
        self.successes += 1.0
        self.recent_successes = min(self.recent_opportunities, self.recent_successes + 1.0)


def _default_stats() -> dict[str, BayesianStat]:
    return {
        "vpip": BayesianStat(prior_success=5.0, prior_failure=15.0),
        "pfr": BayesianStat(prior_success=3.0, prior_failure=17.0),
        "limp": BayesianStat(prior_success=2.0, prior_failure=18.0),
        "three_bet": BayesianStat(prior_success=1.5, prior_failure=18.5),
        "four_bet": BayesianStat(prior_success=1.0, prior_failure=24.0),
        "fold_to_open": BayesianStat(prior_success=11.0, prior_failure=9.0),
        "fold_to_cbet": BayesianStat(prior_success=9.0, prior_failure=11.0),
        "cbet_flop": BayesianStat(prior_success=10.0, prior_failure=10.0),
        "aggression": BayesianStat(prior_success=8.0, prior_failure=12.0),
        "went_showdown": BayesianStat(prior_success=5.0, prior_failure=15.0),
        "won_showdown": BayesianStat(prior_success=10.0, prior_failure=10.0),
        "bluff_revealed": BayesianStat(prior_success=1.0, prior_failure=9.0),
    }


class OpponentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    player_id: str
    name: str
    initial_profile: InitialProfile = InitialProfile.UNKNOWN
    custom_profile: str | None = None
    stats: dict[str, BayesianStat] = Field(default_factory=_default_stats)
    position_stats: dict[str, dict[str, BayesianStat]] = Field(default_factory=dict)
    sizing_sum_by_street: dict[str, float] = Field(default_factory=dict)
    sizing_count_by_street: dict[str, int] = Field(default_factory=dict)
    hands_observed: int = 0
    revealed_hands: int = 0
    observed_bluffs: int = 0
    notes: str = ""
    exploit_enabled: bool = True
    seen_preflop_hands: list[str] = Field(default_factory=list)
    preflop_raise_hands: list[str] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def _stat(self, name: str) -> BayesianStat:
        if name not in self.stats:
            self.stats[name] = BayesianStat()
        return self.stats[name]

    def _position_stat(self, position: str, name: str) -> BayesianStat:
        if position not in self.position_stats:
            self.position_stats[position] = {}
        if name not in self.position_stats[position]:
            self.position_stats[position][name] = BayesianStat()
        return self.position_stats[position][name]

    def observe_action(
        self,
        *,
        hand_id: str,
        street: Street,
        action: ActionKind,
        position: str,
        amount: int = 0,
        pot_before: int = 0,
        facing_raise: bool = False,
        raise_count: int = 0,
        facing_cbet: bool = False,
        is_cbet: bool = False,
        cbet_opportunity: bool = False,
    ) -> None:
        aggressive = action in {ActionKind.BET, ActionKind.RAISE, ActionKind.ALL_IN}
        voluntary = action in {ActionKind.CALL, ActionKind.BET, ActionKind.RAISE, ActionKind.ALL_IN}
        first_preflop_action = street == Street.PREFLOP and hand_id not in self.seen_preflop_hands
        if first_preflop_action:
            self.seen_preflop_hands.append(hand_id)
            self.seen_preflop_hands = self.seen_preflop_hands[-500:]
            self.hands_observed += 1
            self._stat("vpip").observe(voluntary)
            self._stat("pfr").observe(aggressive)
            self._stat("limp").observe(action == ActionKind.CALL and not facing_raise)
            self._position_stat(position, "vpip").observe(voluntary)
            self._position_stat(position, "pfr").observe(aggressive)
            if aggressive:
                self.preflop_raise_hands.append(hand_id)
        elif street == Street.PREFLOP and aggressive and hand_id not in self.preflop_raise_hands:
            self._stat("pfr").promote_latest_failure()
            self._position_stat(position, "pfr").promote_latest_failure()
            self.preflop_raise_hands.append(hand_id)
        self.preflop_raise_hands = self.preflop_raise_hands[-500:]
        if street == Street.PREFLOP and facing_raise:
            self._stat("fold_to_open").observe(action == ActionKind.FOLD)
            if raise_count == 1:
                self._stat("three_bet").observe(action in {ActionKind.RAISE, ActionKind.ALL_IN})
            elif raise_count >= 2:
                self._stat("four_bet").observe(action in {ActionKind.RAISE, ActionKind.ALL_IN})
        if street != Street.PREFLOP and action in {
            ActionKind.CALL,
            ActionKind.BET,
            ActionKind.RAISE,
            ActionKind.ALL_IN,
        }:
            self._stat("aggression").observe(aggressive)
        if facing_cbet:
            self._stat("fold_to_cbet").observe(action == ActionKind.FOLD)
        if street == Street.FLOP and cbet_opportunity:
            self._stat("cbet_flop").observe(is_cbet)
        if amount > 0 and pot_before > 0:
            key = street.value
            self.sizing_sum_by_street[key] = (
                self.sizing_sum_by_street.get(key, 0.0) + amount / pot_before
            )
            self.sizing_count_by_street[key] = self.sizing_count_by_street.get(key, 0) + 1
        self.last_updated = datetime.now(UTC)

    def observe_showdown(self, *, won: bool | None, bluff: bool | None) -> None:
        self.revealed_hands += 1
        self._stat("went_showdown").observe(True)
        if won is not None:
            self._stat("won_showdown").observe(won)
        if bluff is not None:
            self._stat("bluff_revealed").observe(bluff)
            if bluff:
                self.observed_bluffs += 1
        self.last_updated = datetime.now(UTC)

    @property
    def confidence(self) -> float:
        observed = max(
            self.hands_observed,
            max((stat.raw_opportunities for stat in self.stats.values()), default=0),
        )
        if observed < 10:
            return min(0.10, observed / 100.0)
        if observed < 30:
            return 0.10 + (observed - 10) / 30 * 0.15
        if observed < 100:
            return 0.25 + (observed - 30) / 70 * 0.30
        return min(0.85, 0.55 + (observed - 100) / 500 * 0.30)

    @property
    def estimated_profile(self) -> str:
        vpip = self._stat("vpip").mean
        pfr = self._stat("pfr").mean
        aggression = self._stat("aggression").mean
        if self.confidence < 0.12:
            return "inconnu"
        if vpip > 0.42 and pfr < 0.16:
            return "calling_station"
        # Un volume élevé de relances préflop est lui-même un signal agressif
        # robuste, même lorsque peu de décisions postflop ont encore fourni des
        # occasions à la statistique d'agression.
        if vpip > 0.35 and (aggression > 0.52 or pfr > 0.38):
            return "large_agressif"
        if vpip < 0.20 and pfr > 0.12:
            return "serré_agressif"
        if vpip < 0.18:
            return "très_serré"
        if aggression > 0.62:
            return "très_agressif"
        return "équilibré_inconnu"

    def public_view(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "initial_profile": self.initial_profile,
            "estimated_profile": self.estimated_profile,
            "confidence": self.confidence,
            "hands_observed": self.hands_observed,
            "revealed_hands": self.revealed_hands,
            "observed_bluffs": self.observed_bluffs,
            "notes": self.notes,
            "exploit_enabled": self.exploit_enabled,
            "stats": {
                name: {
                    "value": stat.mean,
                    "recent_value": stat.recent_mean,
                    "opportunities": stat.raw_opportunities,
                    "confidence": stat.confidence,
                    "credible_interval": stat.credible_interval,
                }
                for name, stat in self.stats.items()
            },
            "position_stats": {
                position: {
                    name: {
                        "value": stat.mean,
                        "opportunities": stat.raw_opportunities,
                        "confidence": stat.confidence,
                    }
                    for name, stat in stats.items()
                }
                for position, stats in self.position_stats.items()
            },
            "average_sizing_by_street": {
                street: self.sizing_sum_by_street[street] / count
                for street, count in self.sizing_count_by_street.items()
                if count > 0
            },
            "hypothesis_disclaimer": "Hypothèse statistique, pas certitude psychologique.",
        }

    def merge(self, other: OpponentModel) -> None:
        for name, stat in other.stats.items():
            self._stat(name).merge(stat)
        for position, stats in other.position_stats.items():
            for name, stat in stats.items():
                self._position_stat(position, name).merge(stat)
        self.hands_observed += other.hands_observed
        self.revealed_hands += other.revealed_hands
        self.observed_bluffs += other.observed_bluffs
        for street, total in other.sizing_sum_by_street.items():
            self.sizing_sum_by_street[street] = self.sizing_sum_by_street.get(street, 0.0) + total
            self.sizing_count_by_street[street] = self.sizing_count_by_street.get(
                street, 0
            ) + other.sizing_count_by_street.get(street, 0)
        self.last_updated = datetime.now(UTC)
