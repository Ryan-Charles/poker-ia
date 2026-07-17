from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ChipAmount = Annotated[int, Field(ge=0)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Unit(StrEnum):
    CHIPS = "chips"
    FICTIONAL_EUROS = "fictional_euros"
    BIG_BLINDS = "big_blinds"


class GameMode(StrEnum):
    CASH = "cash"
    TOURNAMENT = "tournament"


class AnteType(StrEnum):
    NONE = "none"
    CLASSIC = "classic"
    BIG_BLIND = "big_blind"


class InitialProfile(StrEnum):
    UNKNOWN = "unknown"
    VERY_TIGHT = "very_tight"
    TAG = "tight_aggressive"
    LAG = "loose_aggressive"
    LOOSE_PASSIVE = "loose_passive"
    CALLING_STATION = "calling_station"
    VERY_AGGRESSIVE = "very_aggressive"
    UNPREDICTABLE = "unpredictable"
    CUSTOM = "custom"


class PlayerStatus(StrEnum):
    ACTIVE = "active"
    FOLDED = "folded"
    ALL_IN = "all_in"
    ABSENT = "absent"
    ELIMINATED = "eliminated"


class Street(StrEnum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    COMPLETE = "complete"


class HandStatus(StrEnum):
    ACTIVE = "active"
    AWAITING_CARDS = "awaiting_cards"
    SHOWDOWN = "showdown"
    COMPLETE = "complete"


class ActionKind(StrEnum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


class EventType(StrEnum):
    POST_ANTE = "post_ante"
    POST_SMALL_BLIND = "post_small_blind"
    POST_BIG_BLIND = "post_big_blind"
    ACTION = "action"
    SET_CARD = "set_card"
    CLEAR_CARD = "clear_card"
    SHOWDOWN = "showdown"


class AnalysisLevel(StrEnum):
    FAST = "fast"
    DEEP = "deep"
    EXPERT = "expert"


class PlayerConfig(ApiModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=40)
    seat: int = Field(ge=0, le=8)
    stack: ChipAmount
    status: Literal[PlayerStatus.ACTIVE, PlayerStatus.ABSENT, PlayerStatus.ELIMINATED] = (
        PlayerStatus.ACTIVE
    )
    initial_profile: InitialProfile = InitialProfile.UNKNOWN
    notes: str = Field(default="", max_length=4000)
    custom_profile: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def normalize_frontend_profile(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        profile_aliases = {"tag": "tight_aggressive", "lag": "loose_aggressive"}
        if data.get("initial_profile") in profile_aliases:
            data["initial_profile"] = profile_aliases[data["initial_profile"]]
        if data.get("status") == "away":
            data["status"] = "absent"
        return data

    @model_validator(mode="after")
    def enforce_hero(self) -> PlayerConfig:
        if self.status == PlayerStatus.ACTIVE and self.stack <= 0:
            raise ValueError("Un joueur actif doit posséder au moins un jeton")
        if self.id == "hero" and self.name != "Ryanchl":
            raise ValueError("Le joueur hero doit toujours s'appeler Ryanchl")
        if self.id != "hero" and self.name.casefold() == "ryanchl":
            raise ValueError("Le nom Ryanchl est réservé au joueur principal")
        if self.initial_profile == InitialProfile.CUSTOM and not self.custom_profile:
            raise ValueError("Un profil personnalisé doit contenir une description")
        return self


class BlindLevel(ApiModel):
    after_hands: int | None = Field(default=None, ge=1)
    after_minutes: int | None = Field(default=None, ge=1)
    small_blind: int = Field(gt=0)
    big_blind: int = Field(gt=0)
    ante: ChipAmount = 0

    @model_validator(mode="after")
    def validate_trigger(self) -> BlindLevel:
        if (self.after_hands is None) == (self.after_minutes is None):
            raise ValueError("Un niveau doit définir soit after_hands, soit after_minutes")
        if self.big_blind < self.small_blind:
            raise ValueError("La grosse blinde du niveau doit être au moins égale à la petite")
        return self


class SessionCreate(ApiModel):
    players: list[PlayerConfig] = Field(min_length=2, max_length=8)
    small_blind: int = Field(gt=0)
    big_blind: int = Field(gt=0)
    ante: ChipAmount = 0
    ante_type: AnteType = AnteType.NONE
    unit: Unit = Unit.CHIPS
    mode: GameMode = GameMode.CASH
    button_player_id: str
    small_blind_player_id: str | None = None
    big_blind_player_id: str | None = None
    blind_increase_every_hands: int | None = Field(default=None, ge=1)
    blind_increase_factor: float = Field(default=1.5, gt=1.0, le=10.0)
    quiz_mode: bool = False
    session_name: str = Field(default="Session Poker IA", min_length=1, max_length=100)
    blind_levels: list[BlindLevel] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_frontend_contract(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        aliases = {
            "game_mode": "mode",
            "dealer_id": "button_player_id",
            "small_blind_id": "small_blind_player_id",
            "big_blind_id": "big_blind_player_id",
        }
        for source, target in aliases.items():
            if source in data and target not in data:
                data[target] = data[source]
            data.pop(source, None)
        player_count = data.pop("player_count", None)
        if (
            player_count is not None
            and "players" in data
            and int(player_count) != len(data["players"])
        ):
            raise ValueError("player_count doit correspondre au nombre de joueurs fournis")
        advice_mode = data.pop("advice_mode", None)
        if advice_mode is not None and "quiz_mode" not in data:
            data["quiz_mode"] = advice_mode == "quiz"
        ante_aliases = {"big_blind_ante": "big_blind"}
        if data.get("ante_type") in ante_aliases:
            data["ante_type"] = ante_aliases[data["ante_type"]]
        return data

    @model_validator(mode="after")
    def validate_table(self) -> SessionCreate:
        if self.big_blind < self.small_blind:
            raise ValueError("La grosse blinde doit être au moins égale à la petite blinde")
        ids = [player.id for player in self.players]
        seats = [player.seat for player in self.players]
        if len(ids) != len(set(ids)):
            raise ValueError("Les identifiants de joueurs doivent être uniques")
        if len(seats) != len(set(seats)):
            raise ValueError("Les sièges doivent être uniques")
        if ids.count("hero") != 1:
            raise ValueError("La table doit contenir exactement un joueur hero nommé Ryanchl")
        active = [p for p in self.players if p.status == PlayerStatus.ACTIVE]
        if len(active) < 2:
            raise ValueError("Au moins deux joueurs actifs sont nécessaires")
        active_ids = {p.id for p in active}
        for role, player_id in {
            "bouton": self.button_player_id,
            "petite blinde": self.small_blind_player_id,
            "grosse blinde": self.big_blind_player_id,
        }.items():
            if player_id is not None and player_id not in active_ids:
                raise ValueError(f"Le joueur indiqué pour {role} doit être actif")
        if self.ante_type == AnteType.NONE and self.ante != 0:
            raise ValueError("Un ante non nul nécessite un type d'ante")
        if self.mode == GameMode.CASH and self.blind_increase_every_hands is not None:
            raise ValueError("L'augmentation automatique des blindes est réservée au tournoi")
        if self.mode == GameMode.CASH and self.blind_levels:
            raise ValueError("Les niveaux de blindes sont réservés au mode tournoi")
        if self.blind_levels:
            trigger_kinds = {
                "hands" if level.after_hands is not None else "minutes"
                for level in self.blind_levels
            }
            if len(trigger_kinds) != 1:
                raise ValueError("Tous les niveaux doivent utiliser la même unité de déclenchement")
            thresholds: list[int] = []
            for level in self.blind_levels:
                threshold = (
                    level.after_hands if level.after_hands is not None else level.after_minutes
                )
                if threshold is None:
                    raise ValueError("Un niveau de blindes doit posséder un seuil")
                thresholds.append(threshold)
            if thresholds != sorted(thresholds) or len(thresholds) != len(set(thresholds)):
                raise ValueError("Les niveaux de blindes doivent être strictement croissants")
        if len(active) == 2:
            if (
                self.small_blind_player_id is not None
                and self.small_blind_player_id != self.button_player_id
            ):
                raise ValueError(
                    "En heads-up, le bouton doit obligatoirement être la petite blinde"
                )
            if (
                self.big_blind_player_id is not None
                and self.big_blind_player_id == self.button_player_id
            ):
                raise ValueError(
                    "En heads-up, le joueur au bouton ne peut pas être la grosse blinde"
                )
        elif len(active) >= 3:
            ordered = sorted(active, key=lambda player: player.seat)
            button_index = next(
                index for index, player in enumerate(ordered) if player.id == self.button_player_id
            )
            expected_small = ordered[(button_index + 1) % len(ordered)].id
            expected_big = ordered[(button_index + 2) % len(ordered)].id
            if (
                self.small_blind_player_id is not None
                and self.small_blind_player_id != expected_small
            ) or (
                self.big_blind_player_id is not None and self.big_blind_player_id != expected_big
            ):
                raise ValueError(
                    "L'ordre des blindes doit suivre le bouton dans le sens des sièges: "
                    "bouton, SB, BB"
                )
        return self


class PlayerState(ApiModel):
    id: str
    name: str
    seat: int
    position: str = ""
    stack: ChipAmount
    starting_stack: ChipAmount
    status: PlayerStatus
    street_contribution: ChipAmount = 0
    total_contribution: ChipAmount = 0
    dead_money_contribution: ChipAmount = 0
    last_action: str | None = None
    can_raise: bool = True
    has_acted: bool = False
    last_bet_faced: ChipAmount = 0
    initial_profile: InitialProfile = InitialProfile.UNKNOWN
    notes: str = ""
    estimated_profile: str = "inconnu"
    profile_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    hands_observed: ChipAmount = 0


class LegalAction(ApiModel):
    action: ActionKind
    enabled: bool
    reason: str | None = None
    to_call: ChipAmount = 0
    min_total: ChipAmount | None = None
    max_total: ChipAmount | None = None
    is_all_in_only: bool = False


class PotView(ApiModel):
    index: int
    name: str
    amount: ChipAmount
    eligible_player_ids: list[str]
    winner_ids: list[str] = Field(default_factory=list)
    shares: dict[str, ChipAmount] = Field(default_factory=dict)


class HandEvent(ApiModel):
    id: str
    sequence: int
    type: EventType
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor_id: str | None = None
    action: ActionKind | None = None
    amount: ChipAmount | None = None
    total: ChipAmount | None = None
    slot: str | None = None
    card: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reversible: bool = True


class HandResult(ApiModel):
    status: Literal["won", "lost", "split", "incomplete", "won_without_showdown"]
    winners: list[str]
    total_pot: ChipAmount
    pots: list[PotView]
    received: dict[str, ChipAmount]
    net_results: dict[str, int]
    refunds: dict[str, ChipAmount] = Field(default_factory=dict)
    hand_ranks: dict[str, str] = Field(default_factory=dict)
    best_five: dict[str, list[str]] = Field(default_factory=dict)
    resolution_method: Literal["automatic_showdown", "manual_assignment", "fold_win"]
    cards_complete: bool


class HandState(ApiModel):
    id: str
    number: int
    street: Street
    status: HandStatus
    button_player_id: str
    small_blind_player_id: str
    big_blind_player_id: str
    actor_id: str | None
    players: list[PlayerState]
    board: list[str] = Field(default_factory=list)
    hero_cards: list[str] = Field(default_factory=list)
    selected_cards: dict[str, str] = Field(default_factory=dict)
    revealed_hands: dict[str, list[str]] = Field(default_factory=dict)
    current_bet: ChipAmount = 0
    last_full_raise: ChipAmount
    pot: ChipAmount = 0
    pots: list[PotView] = Field(default_factory=list)
    needs_action: list[str] = Field(default_factory=list)
    runout_mode: bool = False
    awaiting_slots: list[str] = Field(default_factory=list)
    legal_actions: list[LegalAction] = Field(default_factory=list)
    events: list[HandEvent] = Field(default_factory=list)
    can_undo: bool = False
    can_redo: bool = False
    result: HandResult | None = None
    refunds: dict[str, ChipAmount] = Field(default_factory=dict)


class ActionRequest(ApiModel):
    action: ActionKind
    amount: ChipAmount | None = None


class CardRequest(ApiModel):
    slot: Literal["hero_1", "hero_2", "flop_1", "flop_2", "flop_3", "turn", "river"]
    card: str


class ShowdownRequest(ApiModel):
    revealed_hands: dict[str, list[str] | None] = Field(default_factory=dict)
    mucked_player_ids: list[str] = Field(default_factory=list)
    manual_winners: dict[int, list[str]] = Field(default_factory=dict)

    @field_validator("revealed_hands")
    @classmethod
    def validate_hands(cls, value: dict[str, list[str] | None]) -> dict[str, list[str] | None]:
        for cards in value.values():
            if cards is not None and len(cards) != 2:
                raise ValueError("Une main révélée doit contenir exactement deux cartes")
        return value


class AnalysisRequest(ApiModel):
    level: AnalysisLevel = AnalysisLevel.FAST
    trials: int | None = Field(default=None, ge=100, le=100_000)
    seed: int | None = None


class ActionEvaluation(ApiModel):
    action: ActionKind
    amount: ChipAmount | None = None
    balanced_ev: float
    exploit_ev: float
    guarded_ev: float
    frequency: float
    acceptable: bool


class Advice(ApiModel):
    id: str
    session_id: str
    hand_id: str
    street: Street
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    primary_action: ActionKind
    recommended_total: ChipAmount | None = None
    frequency: float
    balanced_action: ActionKind
    exploit_action: ActionKind
    sampled_action: ActionKind
    alternatives: list[ActionEvaluation]
    equity: float
    equity_required: float
    pot_odds: float
    spr: float
    effective_stack: ChipAmount
    fold_equity: float
    confidence: float
    analysis_level: AnalysisLevel
    source: str
    precision: Literal["deterministic_table_abstraction", "monte_carlo_estimate"]
    seed: int
    trials: int
    explanation: str
    detailed_explanation: str | None = None
    explanation_pending: bool = True
    limitations: list[str]
    actual_action: ActionKind | None = None
    actual_amount: ChipAmount | None = None
    ev_difference: float | None = None
    result_net: int | None = None


class SessionState(ApiModel):
    session_id: str
    session_name: str
    created_at: datetime
    updated_at: datetime
    config: SessionCreate
    hand: HandState
    advice: Advice | None = None
    advice_count: int = 0
    hands_played: int = 0
    cumulative_hero_result: int = 0
    initial_hero_stack: ChipAmount
    persistence_status: Literal["saved", "pending", "warning"] = "pending"


class PlayerPatch(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    stack: int | None = Field(default=None, ge=0)
    status: Literal[PlayerStatus.ACTIVE, PlayerStatus.ABSENT, PlayerStatus.ELIMINATED] | None = None
    initial_profile: InitialProfile | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="before")
    @classmethod
    def normalize_away(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("status") == "away":
            return {**value, "status": "absent"}
        return value


class PlayerReplace(ApiModel):
    name: str = Field(min_length=1, max_length=40)
    stack: int | None = Field(default=None, ge=0)
    initial_profile: InitialProfile | None = None
    custom_profile: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def normalize_frontend_profile(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        profile_aliases = {"tag": "tight_aggressive", "lag": "loose_aggressive"}
        if data.get("initial_profile") in profile_aliases:
            data["initial_profile"] = profile_aliases[data["initial_profile"]]
        return data

    @model_validator(mode="after")
    def require_custom_profile_description(self) -> PlayerReplace:
        if self.initial_profile == InitialProfile.CUSTOM and not self.custom_profile:
            raise ValueError("Un profil personnalisé doit contenir une description")
        return self


class OpponentPatch(ApiModel):
    notes: str | None = Field(default=None, max_length=4000)
    exploit_enabled: bool | None = None
    initial_profile: InitialProfile | None = None
    custom_profile: str | None = Field(default=None, min_length=1, max_length=2000)
    adaptation_enabled: bool | None = None

    @model_validator(mode="after")
    def require_custom_profile_description(self) -> OpponentPatch:
        if self.initial_profile == InitialProfile.CUSTOM and not self.custom_profile:
            raise ValueError("Une description est obligatoire pour le profil personnalisé")
        return self


class OpponentMerge(ApiModel):
    source_id: str
    target_id: str


class ImportRequest(ApiModel):
    data: dict[str, Any]
    replace_existing: bool = False


class ExitRequest(ApiModel):
    save: bool = True
