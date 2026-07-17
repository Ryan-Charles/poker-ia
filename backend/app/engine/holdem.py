from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.engine.cards import CardError, ensure_unique, normalize_card
from app.engine.evaluator import EvaluatedHand, evaluate_seven
from app.engine.pots import build_pots, odd_chip_order
from app.models import (
    ActionKind,
    ActionRequest,
    AnteType,
    EventType,
    HandEvent,
    HandResult,
    HandState,
    HandStatus,
    LegalAction,
    PlayerConfig,
    PlayerState,
    PlayerStatus,
    PotView,
    SessionCreate,
    ShowdownRequest,
    Street,
)


class PokerRuleError(ValueError):
    """Violation d'une règle de poker exprimable à l'utilisateur."""


SLOT_ORDER = ("hero_1", "hero_2", "flop_1", "flop_2", "flop_3", "turn", "river")
BOARD_SLOTS = ("flop_1", "flop_2", "flop_3", "turn", "river")
STREET_SLOTS = {
    Street.FLOP: ("flop_1", "flop_2", "flop_3"),
    Street.TURN: ("turn",),
    Street.RIVER: ("river",),
}


@dataclass(slots=True)
class EngineExport:
    config: dict[str, Any]
    hand_id: str
    hand_number: int
    button_player_id: str
    players: list[dict[str, Any]]
    events: list[dict[str, Any]]
    cursor: int
    forced_count: int


class HoldemEngine:
    """Moteur event-sourcé d'une main de No-Limit Texas Hold'em."""

    def __init__(
        self,
        config: SessionCreate,
        *,
        hand_number: int = 1,
        hand_id: str | None = None,
        button_player_id: str | None = None,
        players: list[PlayerConfig] | None = None,
    ) -> None:
        self.config = config
        self.hand_id = hand_id or str(uuid4())
        self.hand_number = hand_number
        self.button_player_id = button_player_id or config.button_player_id
        self.initial_players = deepcopy(players or config.players)
        self.events: list[HandEvent] = []
        self.cursor = 0
        self.forced_count = 0
        self._base_state = self._make_base_state()
        self._create_forced_events()
        self.state = self._rebuild()

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> HoldemEngine:
        config = SessionCreate.model_validate(payload["config"])
        players = [PlayerConfig.model_validate(player) for player in payload["players"]]
        engine = cls(
            config,
            hand_number=int(payload["hand_number"]),
            hand_id=str(payload["hand_id"]),
            button_player_id=str(payload["button_player_id"]),
            players=players,
        )
        engine.events = [HandEvent.model_validate(event) for event in payload["events"]]
        engine.cursor = int(payload["cursor"])
        engine.forced_count = int(payload["forced_count"])
        engine.state = engine._rebuild()
        return engine

    def export(self) -> dict[str, Any]:
        return {
            "config": self.config.model_dump(mode="json"),
            "hand_id": self.hand_id,
            "hand_number": self.hand_number,
            "button_player_id": self.button_player_id,
            "players": [player.model_dump(mode="json") for player in self.initial_players],
            "events": [event.model_dump(mode="json") for event in self.events],
            "cursor": self.cursor,
            "forced_count": self.forced_count,
        }

    def _active_configs(self) -> list[PlayerConfig]:
        return sorted(
            (
                player
                for player in self.initial_players
                if player.status == PlayerStatus.ACTIVE and player.stack > 0
            ),
            key=lambda player: player.seat,
        )

    def _next_config(self, player_id: str) -> PlayerConfig:
        active = self._active_configs()
        index = next(index for index, player in enumerate(active) if player.id == player_id)
        return active[(index + 1) % len(active)]

    def _resolve_blinds(self) -> tuple[str, str]:
        active = self._active_configs()
        if len(active) < 2:
            raise PokerRuleError("Au moins deux joueurs avec des jetons sont nécessaires")
        if self.button_player_id not in {player.id for player in active}:
            raise PokerRuleError("Le bouton doit appartenir à un joueur actif")
        if self.hand_number == 1 and self.config.small_blind_player_id is not None:
            small = self.config.small_blind_player_id
        else:
            small = (
                self.button_player_id
                if len(active) == 2
                else self._next_config(self.button_player_id).id
            )
        if self.hand_number == 1 and self.config.big_blind_player_id is not None:
            big = self.config.big_blind_player_id
        else:
            big = self._next_config(small).id
        if small == big:
            raise PokerRuleError("La petite et la grosse blinde doivent être distinctes")
        return small, big

    def _position_names(self, small: str, big: str) -> dict[str, str]:
        active = self._active_configs()
        names: dict[str, str] = {self.button_player_id: "BTN", small: "SB", big: "BB"}
        if len(active) == 2:
            names[self.button_player_id] = "BTN/SB"
            return names
        post_button: list[str] = []
        current = self._next_config(big)
        while current.id != self.button_player_id:
            post_button.append(current.id)
            current = self._next_config(current.id)
        labels_by_count = {
            1: ["UTG"],
            2: ["UTG", "CO"],
            3: ["UTG", "HJ", "CO"],
            4: ["UTG", "MP", "HJ", "CO"],
            5: ["UTG", "UTG+1", "MP", "HJ", "CO"],
        }
        labels = labels_by_count.get(
            len(post_button), [f"MP{index + 1}" for index in range(len(post_button))]
        )
        names.update(dict(zip(post_button, labels, strict=True)))
        return names

    def _make_base_state(self) -> HandState:
        small, big = self._resolve_blinds()
        positions = self._position_names(small, big)
        players = [
            PlayerState(
                id=player.id,
                name=player.name,
                seat=player.seat,
                position=positions.get(player.id, "Absent"),
                stack=player.stack,
                starting_stack=player.stack,
                status=PlayerStatus.ACTIVE
                if player.status == PlayerStatus.ACTIVE
                else player.status,
                initial_profile=player.initial_profile,
                notes=player.notes,
            )
            for player in sorted(self.initial_players, key=lambda item: item.seat)
        ]
        preflop_actor = (
            self.button_player_id if len(self._active_configs()) == 2 else self._next_config(big).id
        )
        needs = [player.id for player in players if player.status == PlayerStatus.ACTIVE]
        return HandState(
            id=self.hand_id,
            number=self.hand_number,
            street=Street.PREFLOP,
            status=HandStatus.ACTIVE,
            button_player_id=self.button_player_id,
            small_blind_player_id=small,
            big_blind_player_id=big,
            actor_id=preflop_actor,
            players=players,
            last_full_raise=self.config.big_blind,
            needs_action=needs,
        )

    def _new_event(self, event_type: EventType, **kwargs: Any) -> HandEvent:
        return HandEvent(
            id=str(uuid4()),
            sequence=len(self.events),
            type=event_type,
            **kwargs,
        )

    def _create_forced_events(self) -> None:
        active_ids = [
            player.id for player in self._base_state.players if player.status == PlayerStatus.ACTIVE
        ]
        if self.config.ante_type == AnteType.CLASSIC:
            for player_id in active_ids:
                self.events.append(
                    self._new_event(
                        EventType.POST_ANTE,
                        actor_id=player_id,
                        amount=self.config.ante,
                        reversible=False,
                    )
                )
        self.events.extend(
            [
                self._new_event(
                    EventType.POST_SMALL_BLIND,
                    actor_id=self._base_state.small_blind_player_id,
                    amount=self.config.small_blind,
                    reversible=False,
                ),
                self._new_event(
                    EventType.POST_BIG_BLIND,
                    actor_id=self._base_state.big_blind_player_id,
                    amount=self.config.big_blind,
                    reversible=False,
                ),
            ]
        )
        if self.config.ante_type == AnteType.BIG_BLIND:
            self.events.append(
                self._new_event(
                    EventType.POST_ANTE,
                    actor_id=self._base_state.big_blind_player_id,
                    amount=self.config.ante,
                    reversible=False,
                )
            )
        self.forced_count = len(self.events)
        self.cursor = self.forced_count

    @staticmethod
    def _player(state: HandState, player_id: str) -> PlayerState:
        try:
            return next(player for player in state.players if player.id == player_id)
        except StopIteration as exc:
            raise PokerRuleError(f"Joueur inconnu: {player_id}") from exc

    @staticmethod
    def _actionable(player: PlayerState) -> bool:
        return player.status == PlayerStatus.ACTIVE and player.stack > 0

    def _rebuild(self) -> HandState:
        state = self._base_state.model_copy(deep=True)
        for event in self.events[: self.cursor]:
            self._apply_event(state, event)
        has_voluntary_event = any(
            event.type
            in {EventType.ACTION, EventType.SET_CARD, EventType.CLEAR_CARD, EventType.SHOWDOWN}
            for event in self.events[: self.cursor]
        )
        actionable_after_forced = [player for player in state.players if self._actionable(player)]
        lone_player_has_no_forced_decision = len(
            actionable_after_forced
        ) == 1 and actionable_after_forced[0].street_contribution >= max(
            state.current_bet, self.config.big_blind
        )
        if (
            not has_voluntary_event
            and state.status == HandStatus.ACTIVE
            and (not state.needs_action or lone_player_has_no_forced_decision)
            and len(
                [
                    player
                    for player in state.players
                    if player.status
                    not in {PlayerStatus.FOLDED, PlayerStatus.ABSENT, PlayerStatus.ELIMINATED}
                ]
            )
            > 1
        ):
            self._close_betting_round(state)
        state.events = [event.model_copy(deep=True) for event in self.events[: self.cursor]]
        state.can_undo = self.cursor > self.forced_count
        state.can_redo = self.cursor < len(self.events)
        state.pot = sum(player.total_contribution for player in state.players)
        if state.status != HandStatus.COMPLETE:
            state.pots = list(build_pots(state.players).pots)
        state.legal_actions = self._legal_actions(state)
        return state

    def _apply_event(self, state: HandState, event: HandEvent) -> None:
        if event.type in {
            EventType.POST_ANTE,
            EventType.POST_SMALL_BLIND,
            EventType.POST_BIG_BLIND,
        }:
            self._apply_forced(state, event)
        elif event.type == EventType.ACTION:
            self._apply_action(state, event)
        elif event.type == EventType.SET_CARD:
            self._apply_card(state, event)
        elif event.type == EventType.CLEAR_CARD:
            self._apply_clear_card(state, event)
        elif event.type == EventType.SHOWDOWN:
            self._apply_showdown(state, event)

    def _apply_forced(self, state: HandState, event: HandEvent) -> None:
        if event.actor_id is None or event.amount is None:
            raise PokerRuleError("Événement forcé incomplet")
        player = self._player(state, event.actor_id)
        paid = min(event.amount, player.stack)
        player.stack -= paid
        player.total_contribution += paid
        if event.type == EventType.POST_ANTE and self.config.ante_type == AnteType.BIG_BLIND:
            player.dead_money_contribution += paid
        if event.type != EventType.POST_ANTE:
            player.street_contribution += paid
            state.current_bet = max(state.current_bet, player.street_contribution)
        player.last_action = event.type.value
        if player.stack == 0:
            player.status = PlayerStatus.ALL_IN
            state.needs_action = [
                player_id for player_id in state.needs_action if player_id != player.id
            ]
        self._repair_actor(state)

    def legal_actions(self) -> list[LegalAction]:
        return self._legal_actions(self.state)

    def adjust_stack(self, player_id: str, stack: int) -> HandState:
        """Ajuste le tapis restant sans réécrire les actions déjà jouées.

        Le montant saisi représente le tapis réellement disponible *maintenant*.
        On applique donc l'écart au tapis de début de main, puis on rejoue le
        journal existant. Les blindes, mises et relances déjà engagées restent
        identiques, tandis que les actions suivantes utilisent immédiatement le
        nouveau tapis.
        """
        current = self._player(self.state, player_id)
        if stack < 0:
            raise PokerRuleError("Le tapis ne peut pas être négatif")
        if stack == current.stack:
            return self.state
        initial = next((player for player in self.initial_players if player.id == player_id), None)
        if initial is None:
            raise PokerRuleError(f"Joueur inconnu: {player_id}")
        adjusted_initial_stack = initial.stack + stack - current.stack
        if adjusted_initial_stack <= 0 and initial.status == PlayerStatus.ACTIVE:
            raise PokerRuleError(
                "Un joueur assis doit conserver un tapis positif; "
                "retirez-le de la table s'il n'a plus de jetons"
            )
        self.initial_players = [
            player.model_copy(update={"stack": adjusted_initial_stack})
            if player.id == player_id
            else player
            for player in self.initial_players
        ]
        self._base_state = self._make_base_state()
        self.state = self._rebuild()
        return self.state

    def _legal_actions(self, state: HandState) -> list[LegalAction]:
        disabled = [
            LegalAction(action=action, enabled=False, reason="Aucun joueur ne doit agir")
            for action in ActionKind
        ]
        if state.status != HandStatus.ACTIVE or state.actor_id is None:
            return disabled
        player = self._player(state, state.actor_id)
        if not self._actionable(player):
            return disabled
        effective_bet = (
            max(state.current_bet, self.config.big_blind)
            if state.street == Street.PREFLOP
            else state.current_bet
        )
        to_call = max(0, effective_bet - player.street_contribution)
        max_total = player.street_contribution + player.stack
        actionable_count = sum(self._actionable(other) for other in state.players)
        live_count = sum(
            other.status not in {PlayerStatus.FOLDED, PlayerStatus.ABSENT, PlayerStatus.ELIMINATED}
            for other in state.players
        )
        dry_side_pot = actionable_count == 1 and live_count > 1
        actions: dict[ActionKind, LegalAction] = {
            action: LegalAction(
                action=action, enabled=False, reason="Action non disponible", to_call=to_call
            )
            for action in ActionKind
        }
        actions[ActionKind.FOLD] = LegalAction(
            action=ActionKind.FOLD, enabled=True, to_call=to_call
        )
        if to_call == 0:
            actions[ActionKind.CHECK] = LegalAction(action=ActionKind.CHECK, enabled=True)
            actions[ActionKind.CALL].reason = "Rien à suivre"
        else:
            call_amount = min(to_call, player.stack)
            actions[ActionKind.CALL] = LegalAction(
                action=ActionKind.CALL,
                enabled=True,
                to_call=call_amount,
                min_total=player.street_contribution + call_amount,
                max_total=player.street_contribution + call_amount,
                is_all_in_only=player.stack <= to_call,
            )
            actions[ActionKind.CHECK].reason = f"Il faut suivre {to_call} ou se coucher"
        if state.current_bet == 0:
            minimum = min(self.config.big_blind, max_total)
            actions[ActionKind.BET] = LegalAction(
                action=ActionKind.BET,
                enabled=max_total > 0 and not dry_side_pot,
                reason="Aucun adversaire ne peut suivre une mise" if dry_side_pot else None,
                min_total=minimum,
                max_total=max_total,
                is_all_in_only=max_total < self.config.big_blind,
            )
            actions[ActionKind.RAISE].reason = "Aucune mise à relancer"
        else:
            minimum = effective_bet + state.last_full_raise
            if dry_side_pot:
                actions[ActionKind.RAISE].reason = "Aucun adversaire ne peut suivre une relance"
            elif max_total <= effective_bet:
                actions[ActionKind.RAISE].reason = "Le tapis ne dépasse pas le montant à suivre"
            elif not player.can_raise:
                actions[
                    ActionKind.RAISE
                ].reason = "La relance incomplète à tapis n'a pas rouvert les enchères"
            else:
                actions[ActionKind.RAISE] = LegalAction(
                    action=ActionKind.RAISE,
                    enabled=True,
                    min_total=min(minimum, max_total),
                    max_total=max_total,
                    is_all_in_only=max_total < minimum,
                )
            actions[ActionKind.BET].reason = "Une mise existe déjà: utilisez Relancer"
        all_in_reopens = max_total <= effective_bet or (player.can_raise and not dry_side_pot)
        actions[ActionKind.ALL_IN] = LegalAction(
            action=ActionKind.ALL_IN,
            enabled=player.stack > 0 and all_in_reopens,
            reason=(
                None
                if all_in_reopens
                else (
                    "La relance incomplète n'a pas rouvert les enchères; "
                    "seul suivre ou se coucher est permis"
                )
            ),
            to_call=min(to_call, player.stack),
            min_total=max_total,
            max_total=max_total,
            is_all_in_only=True,
        )
        return [actions[action] for action in ActionKind]

    def take_action(self, request: ActionRequest) -> HandState:
        if self.state.actor_id is None:
            raise PokerRuleError("Aucun joueur ne doit agir")
        legal = {action.action: action for action in self.state.legal_actions}
        descriptor = legal[request.action]
        if not descriptor.enabled:
            raise PokerRuleError(descriptor.reason or "Action illégale")
        player = self._player(self.state, self.state.actor_id)
        total: int | None = None
        amount: int | None = None
        if request.action in {ActionKind.BET, ActionKind.RAISE}:
            if request.amount is None:
                raise PokerRuleError("Le montant total à atteindre est requis")
            total = request.amount
            max_total = descriptor.max_total or 0
            min_total = descriptor.min_total or 0
            if total > max_total or total <= self.state.current_bet:
                raise PokerRuleError(f"Le total doit être compris entre {min_total} et {max_total}")
            if total < min_total and total != max_total:
                raise PokerRuleError(f"La relance minimale totale est {min_total}")
            amount = total - player.street_contribution
        elif request.action == ActionKind.ALL_IN:
            total = player.street_contribution + player.stack
            amount = player.stack
        elif request.action == ActionKind.CALL:
            effective_bet = (
                max(self.state.current_bet, self.config.big_blind)
                if self.state.street == Street.PREFLOP
                else self.state.current_bet
            )
            amount = min(effective_bet - player.street_contribution, player.stack)
            total = player.street_contribution + amount
        resolved_action = self._resolved_action_for_event(request.action, total, self.state, player)
        event = self._new_event(
            EventType.ACTION,
            actor_id=player.id,
            action=request.action,
            amount=amount,
            total=total,
            payload={
                "street": self.state.street.value,
                "pot_before": self.state.pot,
                "player_name": player.name,
                "position": player.position,
                "facing_raise": self.state.current_bet > self.config.big_blind,
                "raise_count": sum(
                    event.payload.get("resolved_action", event.action.value if event.action else "")
                    in {ActionKind.BET.value, ActionKind.RAISE.value}
                    for event in self.state.events
                    if event.type == EventType.ACTION and event.action is not None
                ),
                "resolved_action": resolved_action,
                "is_cbet": self._is_continuation_bet(request.action, self.state),
                "cbet_opportunity": self._is_cbet_opportunity(self.state),
                "facing_cbet": self._is_facing_continuation_bet(self.state),
            },
        )
        return self._append(event)

    def _resolved_action_for_event(
        self,
        action: ActionKind,
        total: int | None,
        state: HandState,
        player: PlayerState,
    ) -> str:
        if action != ActionKind.ALL_IN:
            return action.value
        effective_bet = (
            max(state.current_bet, self.config.big_blind)
            if state.street == Street.PREFLOP
            else state.current_bet
        )
        if (total or player.street_contribution) <= effective_bet:
            return ActionKind.CALL.value
        return (ActionKind.BET if state.current_bet == 0 else ActionKind.RAISE).value

    @staticmethod
    def _preflop_aggressor(state: HandState) -> str | None:
        aggressor = None
        for event in state.events:
            if (
                event.type == EventType.ACTION
                and event.payload.get("street") == Street.PREFLOP.value
                and event.payload.get("resolved_action", event.action.value if event.action else "")
                in {ActionKind.BET.value, ActionKind.RAISE.value}
            ):
                aggressor = event.actor_id
        return aggressor

    def _is_continuation_bet(self, action: ActionKind, state: HandState) -> bool:
        if state.street != Street.FLOP or state.current_bet != 0:
            return False
        return action in {ActionKind.BET, ActionKind.ALL_IN} and (
            state.actor_id == self._preflop_aggressor(state)
        )

    def _is_cbet_opportunity(self, state: HandState) -> bool:
        return (
            state.street == Street.FLOP
            and state.current_bet == 0
            and state.actor_id == self._preflop_aggressor(state)
        )

    def _is_facing_continuation_bet(self, state: HandState) -> bool:
        if state.street != Street.FLOP or state.current_bet <= 0:
            return False
        aggressor = self._preflop_aggressor(state)
        last_aggression = next(
            (
                event
                for event in reversed(state.events)
                if event.type == EventType.ACTION
                and event.payload.get("street") == Street.FLOP.value
                and event.payload.get("resolved_action", event.action.value if event.action else "")
                in {ActionKind.BET.value, ActionKind.RAISE.value}
            ),
            None,
        )
        return last_aggression is not None and last_aggression.actor_id == aggressor

    def _append(self, event: HandEvent) -> HandState:
        if self.cursor < len(self.events):
            self.events = self.events[: self.cursor]
        event.sequence = len(self.events)
        self.events.append(event)
        self.cursor += 1
        self.state = self._rebuild()
        return self.state

    def _apply_action(self, state: HandState, event: HandEvent) -> None:
        if event.actor_id is None or event.action is None:
            raise PokerRuleError("Action incomplète dans le journal")
        player = self._player(state, event.actor_id)
        action = event.action
        previous_bet = state.current_bet
        state.needs_action = [
            player_id for player_id in state.needs_action if player_id != player.id
        ]
        player.has_acted = True
        player.can_raise = False
        if action == ActionKind.FOLD:
            player.status = PlayerStatus.FOLDED
            player.last_action = "fold"
        elif action == ActionKind.CHECK:
            player.last_action = "check"
        else:
            target = event.total if event.total is not None else player.street_contribution
            target = min(target, player.street_contribution + player.stack)
            paid = max(0, target - player.street_contribution)
            player.stack -= paid
            player.street_contribution += paid
            player.total_contribution += paid
            nominal_blind_call = (
                action == ActionKind.CALL
                and state.street == Street.PREFLOP
                and previous_bet < self.config.big_blind
                and target > previous_bet
            )
            if nominal_blind_call:
                state.current_bet = target
                player.last_action = "all_in_call" if player.stack == 0 else "call"
                waiting = set(state.needs_action)
                waiting.update(
                    other.id
                    for other in state.players
                    if other.id != player.id
                    and self._actionable(other)
                    and other.street_contribution < target
                )
                state.needs_action = self._clockwise_ids(state, waiting)
            elif target <= previous_bet:
                player.last_action = "all_in_call" if player.stack == 0 else "call"
            else:
                effective_previous = (
                    max(previous_bet, self.config.big_blind)
                    if state.street == Street.PREFLOP
                    else previous_bet
                )
                increase = target - effective_previous
                opening_bet = previous_bet == 0
                opening_full = opening_bet and target >= self.config.big_blind
                full_raise = opening_full or increase >= state.last_full_raise
                state.current_bet = target
                player.last_action = (
                    "all_in" if player.stack == 0 else ("bet" if opening_bet else "raise")
                )
                actionable_others = [
                    other
                    for other in state.players
                    if other.id != player.id and self._actionable(other)
                ]
                if full_raise:
                    if opening_full:
                        state.last_full_raise = target
                    elif not opening_full:
                        state.last_full_raise = increase
                    for other in actionable_others:
                        other.can_raise = True
                    state.needs_action = [other.id for other in actionable_others]
                else:
                    waiting = set(state.needs_action)
                    waiting.update(
                        other.id
                        for other in actionable_others
                        if other.street_contribution < state.current_bet
                    )
                    for other in actionable_others:
                        cumulative_increase = state.current_bet - other.last_bet_faced
                        if other.has_acted and cumulative_increase >= state.last_full_raise:
                            other.can_raise = True
                    state.needs_action = self._clockwise_ids(state, waiting)
            if player.stack == 0:
                player.status = PlayerStatus.ALL_IN
        player.last_bet_faced = state.current_bet
        remaining = [
            other
            for other in state.players
            if other.status
            not in {PlayerStatus.FOLDED, PlayerStatus.ABSENT, PlayerStatus.ELIMINATED}
        ]
        if len(remaining) == 1:
            self._award_fold_win(state, remaining[0].id)
            return
        state.needs_action = [
            player_id
            for player_id in state.needs_action
            if self._actionable(self._player(state, player_id))
        ]
        if not state.needs_action:
            self._close_betting_round(state)
            return
        state.actor_id = self._next_waiting(state, event.actor_id)

    def _clockwise_ids(self, state: HandState, player_ids: set[str]) -> list[str]:
        ordered = sorted(state.players, key=lambda player: player.seat)
        return [player.id for player in ordered if player.id in player_ids]

    def _next_waiting(self, state: HandState, after_id: str) -> str | None:
        ordered = sorted(state.players, key=lambda player: player.seat)
        start = next(index for index, player in enumerate(ordered) if player.id == after_id)
        waiting = set(state.needs_action)
        for offset in range(1, len(ordered) + 1):
            candidate = ordered[(start + offset) % len(ordered)]
            if candidate.id in waiting and self._actionable(candidate):
                return candidate.id
        return None

    def _repair_actor(self, state: HandState) -> None:
        if state.actor_id is None:
            return
        actor = self._player(state, state.actor_id)
        if not self._actionable(actor):
            state.actor_id = self._next_waiting(state, actor.id)

    def _refund_street_uncalled(self, state: HandState) -> dict[str, int]:
        contributions = {player.id: player.street_contribution for player in state.players}
        highest = max(contributions.values(), default=0)
        highest_ids = [
            player_id
            for player_id, amount in contributions.items()
            if amount == highest and amount > 0
        ]
        if len(highest_ids) != 1:
            return {}
        second = max((amount for amount in contributions.values() if amount < highest), default=0)
        refund = highest - second
        if refund <= 0:
            return {}
        player = self._player(state, highest_ids[0])
        player.street_contribution -= refund
        player.total_contribution -= refund
        player.stack += refund
        if player.status == PlayerStatus.ALL_IN and player.stack > 0:
            player.status = PlayerStatus.ACTIVE
        state.current_bet = second
        state.refunds[player.id] = state.refunds.get(player.id, 0) + refund
        return {player.id: refund}

    def _close_betting_round(self, state: HandState) -> None:
        self._refund_street_uncalled(state)
        state.actor_id = None
        if state.street == Street.RIVER:
            self._enter_showdown(state)
            return
        actionable = [player for player in state.players if self._actionable(player)]
        state.runout_mode = len(actionable) <= 1
        next_street = {
            Street.PREFLOP: Street.FLOP,
            Street.FLOP: Street.TURN,
            Street.TURN: Street.RIVER,
        }[state.street]
        self._prepare_street(state, next_street)

    def _prepare_street(self, state: HandState, street: Street) -> None:
        state.street = street
        state.status = HandStatus.AWAITING_CARDS
        state.current_bet = 0
        state.last_full_raise = self.config.big_blind
        state.needs_action = []
        for player in state.players:
            player.street_contribution = 0
            player.has_acted = False
            player.last_bet_faced = 0
            if self._actionable(player):
                player.can_raise = True
        state.awaiting_slots = [
            slot for slot in STREET_SLOTS[street] if slot not in state.selected_cards
        ]
        if not state.awaiting_slots:
            self._cards_ready(state)

    def _cards_ready(self, state: HandState) -> None:
        state.awaiting_slots = []
        if state.runout_mode:
            if state.street == Street.RIVER:
                self._enter_showdown(state)
            else:
                next_street = Street.TURN if state.street == Street.FLOP else Street.RIVER
                self._prepare_street(state, next_street)
            return
        state.status = HandStatus.ACTIVE
        actionable = [player.id for player in state.players if self._actionable(player)]
        if len(actionable) <= 1:
            state.runout_mode = True
            self._cards_ready(state)
            return
        state.needs_action = actionable
        state.actor_id = self._first_postflop_actor(state)

    def _first_postflop_actor(self, state: HandState) -> str | None:
        ordered = sorted(state.players, key=lambda player: player.seat)
        start = next(
            index for index, player in enumerate(ordered) if player.id == state.button_player_id
        )
        for offset in range(1, len(ordered) + 1):
            candidate = ordered[(start + offset) % len(ordered)]
            if self._actionable(candidate):
                return candidate.id
        return None

    def set_card(self, slot: str, card: str) -> HandState:
        if slot not in SLOT_ORDER:
            raise PokerRuleError("Emplacement de carte inconnu")
        normalized = normalize_card(card)
        if slot in BOARD_SLOTS and (
            self.state.status != HandStatus.AWAITING_CARDS or slot not in self.state.awaiting_slots
        ):
            raise PokerRuleError("Cette carte commune n'est pas attendue à ce stade")
        if self.state.status in {HandStatus.SHOWDOWN, HandStatus.COMPLETE}:
            raise PokerRuleError("La sélection principale est fermée à ce stade")
        used_elsewhere = {value for key, value in self.state.selected_cards.items() if key != slot}
        if normalized in used_elsewhere:
            raise PokerRuleError("Cette carte est déjà utilisée")
        return self._append(self._new_event(EventType.SET_CARD, slot=slot, card=normalized))

    def clear_card(self, slot: str) -> HandState:
        if slot not in self.state.selected_cards:
            raise PokerRuleError("Cet emplacement est déjà vide")
        if slot in BOARD_SLOTS and self.state.status != HandStatus.AWAITING_CARDS:
            raise PokerRuleError(
                "Une carte d'une rue déjà jouée ne peut pas être effacée silencieusement"
            )
        return self._append(self._new_event(EventType.CLEAR_CARD, slot=slot))

    def _apply_card(self, state: HandState, event: HandEvent) -> None:
        if event.slot is None or event.card is None:
            raise PokerRuleError("Événement de carte incomplet")
        state.selected_cards[event.slot] = event.card
        self._sync_cards(state)
        if state.status == HandStatus.AWAITING_CARDS:
            state.awaiting_slots = [
                slot for slot in STREET_SLOTS[state.street] if slot not in state.selected_cards
            ]
            if not state.awaiting_slots:
                self._cards_ready(state)

    def _apply_clear_card(self, state: HandState, event: HandEvent) -> None:
        if event.slot is None:
            raise PokerRuleError("Événement d'effacement incomplet")
        state.selected_cards.pop(event.slot, None)
        self._sync_cards(state)
        if state.status == HandStatus.AWAITING_CARDS and state.street in STREET_SLOTS:
            state.awaiting_slots = [
                slot for slot in STREET_SLOTS[state.street] if slot not in state.selected_cards
            ]

    @staticmethod
    def _sync_cards(state: HandState) -> None:
        state.hero_cards = [
            state.selected_cards[slot]
            for slot in ("hero_1", "hero_2")
            if slot in state.selected_cards
        ]
        state.board = [
            state.selected_cards[slot] for slot in BOARD_SLOTS if slot in state.selected_cards
        ]

    def _enter_showdown(self, state: HandState) -> None:
        state.street = Street.SHOWDOWN
        state.status = HandStatus.SHOWDOWN
        state.actor_id = None
        state.needs_action = []
        state.awaiting_slots = []

    def settle_showdown(self, request: ShowdownRequest) -> HandState:
        if self.state.status != HandStatus.SHOWDOWN:
            raise PokerRuleError("La main n'est pas à l'étape du showdown")
        payload = request.model_dump(mode="json")
        self._validate_showdown_payload(self.state, payload)
        return self._append(self._new_event(EventType.SHOWDOWN, payload=payload))

    def _validate_showdown_payload(self, state: HandState, payload: dict[str, Any]) -> None:
        eligible = {
            player.id
            for player in state.players
            if player.status
            not in {PlayerStatus.FOLDED, PlayerStatus.ABSENT, PlayerStatus.ELIMINATED}
        }
        revealed: dict[str, list[str] | None] = payload["revealed_hands"]
        mucked_list = [str(player_id) for player_id in payload.get("mucked_player_ids", [])]
        if len(mucked_list) != len(set(mucked_list)):
            raise PokerRuleError("Un joueur ne peut pas être marqué mucké plusieurs fois")
        mucked = set(mucked_list)
        if not mucked <= eligible:
            raise PokerRuleError("Un joueur mucké n'est éligible à aucun pot")
        if mucked & set(revealed):
            raise PokerRuleError("Une main ne peut pas être à la fois révélée et muckée")
        if "hero" in revealed:
            raise PokerRuleError(
                "Les cartes de Ryanchl sont déjà connues et ne doivent pas être ressaisies"
            )
        used = list(state.board) + list(state.hero_cards)
        for player_id, cards in revealed.items():
            if player_id not in eligible:
                raise PokerRuleError(f"Le joueur {player_id} n'est éligible à aucun pot")
            if cards is not None:
                used.extend(cards)
        try:
            ensure_unique(used)
        except CardError as exc:
            raise PokerRuleError(str(exc)) from exc
        pots = [
            pot.model_copy(
                update={
                    "eligible_player_ids": [
                        player_id
                        for player_id in pot.eligible_player_ids
                        if player_id not in mucked
                    ]
                }
            )
            for pot in build_pots(state.players).pots
        ]
        if any(not pot.eligible_player_ids for pot in pots):
            raise PokerRuleError("Tous les joueurs éligibles d'un pot ne peuvent pas mucker")
        known = {
            player_id
            for player_id, cards in revealed.items()
            if cards is not None and player_id not in mucked
        }
        if len(state.hero_cards) == 2 and "hero" not in mucked:
            known.add("hero")
        manual: dict[int, list[str]] = {
            int(key): value for key, value in payload["manual_winners"].items()
        }
        for pot_index, listed_winners in manual.items():
            if len(listed_winners) != len(set(listed_winners)):
                raise PokerRuleError(
                    f"Un gagnant manuel du pot {pot_index} est présent plusieurs fois"
                )
        for pot in pots:
            if len(pot.eligible_player_ids) <= 1 or set(pot.eligible_player_ids) <= known:
                continue
            manual_winners = manual.get(pot.index)
            if not manual_winners:
                raise PokerRuleError(
                    f"Le pot {pot.index} nécessite une attribution manuelle "
                    "car des cartes sont inconnues"
                )
            if not set(manual_winners) <= set(pot.eligible_player_ids):
                raise PokerRuleError(f"Un gagnant manuel du pot {pot.index} n'est pas éligible")

    def _apply_showdown(self, state: HandState, event: HandEvent) -> None:
        revealed_raw: dict[str, list[str] | None] = event.payload["revealed_hands"]
        revealed = {
            player_id: [normalize_card(card) for card in cards]
            for player_id, cards in revealed_raw.items()
            if cards is not None
        }
        mucked = set(event.payload.get("mucked_player_ids", []))
        state.revealed_hands = revealed
        known_hands = dict(revealed)
        if len(state.hero_cards) == 2 and "hero" not in mucked:
            known_hands["hero"] = list(state.hero_cards)
        construction = build_pots(state.players)
        for player_id, refund in construction.refunds.items():
            player = self._player(state, player_id)
            player.stack += refund
            player.total_contribution -= refund
        evaluations: dict[str, EvaluatedHand] = {}
        if len(state.board) == 5:
            for player_id, cards in known_hands.items():
                evaluations[player_id] = evaluate_seven(cards + state.board)
        manual: dict[int, list[str]] = {
            int(key): value for key, value in event.payload["manual_winners"].items()
        }
        received = {player.id: 0 for player in state.players}
        settled_pots: list[PotView] = []
        incomplete = False
        for original_pot in construction.pots:
            pot = original_pot.model_copy(
                update={
                    "eligible_player_ids": [
                        player_id
                        for player_id in original_pot.eligible_player_ids
                        if player_id not in mucked
                    ]
                }
            )
            eligible = pot.eligible_player_ids
            if len(eligible) == 1:
                winners = eligible
            elif all(player_id in evaluations for player_id in eligible):
                best_key = max(evaluations[player_id].key for player_id in eligible)
                winners = [
                    player_id for player_id in eligible if evaluations[player_id].key == best_key
                ]
            else:
                winners = manual[pot.index]
                incomplete = True
            share, remainder = divmod(pot.amount, len(winners))
            shares = {winner: share for winner in winners}
            for winner in odd_chip_order(winners, state.players, state.button_player_id)[
                :remainder
            ]:
                shares[winner] += 1
            for winner, amount in shares.items():
                self._player(state, winner).stack += amount
                received[winner] += amount
            settled_pots.append(pot.model_copy(update={"winner_ids": winners, "shares": shares}))
        net = {
            player.id: received[player.id] - player.total_contribution for player in state.players
        }
        hero_wins = [pot for pot in settled_pots if "hero" in pot.winner_ids]
        if incomplete:
            hero_status = "incomplete"
        elif not hero_wins:
            hero_status = "lost"
        elif any(len(pot.winner_ids) > 1 for pot in hero_wins):
            hero_status = "split"
        else:
            hero_status = "won"
        state.result = HandResult(
            status=hero_status,
            winners=sorted({winner for pot in settled_pots for winner in pot.winner_ids}),
            total_pot=sum(pot.amount for pot in settled_pots),
            pots=settled_pots,
            received=received,
            net_results=net,
            refunds={**construction.refunds, **state.refunds},
            hand_ranks={player_id: hand.name for player_id, hand in evaluations.items()},
            best_five={player_id: list(hand.cards) for player_id, hand in evaluations.items()},
            resolution_method="manual_assignment" if incomplete else "automatic_showdown",
            cards_complete=not incomplete,
        )
        state.status = HandStatus.COMPLETE
        state.street = Street.COMPLETE
        state.pots = settled_pots

    def _award_fold_win(self, state: HandState, winner_id: str) -> None:
        street_refunds = self._refund_street_uncalled(state)
        construction = build_pots(state.players)
        for player_id, refund in construction.refunds.items():
            player = self._player(state, player_id)
            player.stack += refund
            player.total_contribution -= refund
        amount = sum(pot.amount for pot in construction.pots)
        winner = self._player(state, winner_id)
        winner.stack += amount
        received = {
            player.id: (amount if player.id == winner_id else 0) for player in state.players
        }
        settled = [
            pot.model_copy(update={"winner_ids": [winner_id], "shares": {winner_id: pot.amount}})
            for pot in construction.pots
        ]
        state.result = HandResult(
            status="won_without_showdown" if winner_id == "hero" else "lost",
            winners=[winner_id],
            total_pot=amount,
            pots=settled,
            received=received,
            net_results={
                player.id: received[player.id] - player.total_contribution
                for player in state.players
            },
            refunds={**construction.refunds, **state.refunds, **street_refunds},
            resolution_method="fold_win",
            cards_complete=False,
        )
        state.status = HandStatus.COMPLETE
        state.street = Street.COMPLETE
        state.actor_id = None
        state.needs_action = []
        state.awaiting_slots = []
        state.pots = settled

    def undo(self) -> HandState:
        if self.cursor <= self.forced_count:
            raise PokerRuleError("Aucune action ne peut être annulée")
        self.cursor -= 1
        self.state = self._rebuild()
        return self.state

    def restart_hand(self) -> HandState:
        """Remet la main courante à son état initial, juste après les mises forcées.

        Tronque le journal d'événements pour ne garder que les événements forcés
        produits par `_create_forced_events` (antes/blindes), vide la pile redo
        et reconstruit l'état via `_rebuild`. Comme les événements forcés et
        l'état de base sont entièrement déterminés par la configuration, le
        bouton, le numéro de main et les joueurs de départ, le résultat est
        équivalent à celui d'un moteur fraîchement construit avec ces mêmes
        paramètres: aucune carte ni action volontaire ne subsiste.
        """
        self.events = self.events[: self.forced_count]
        self.cursor = self.forced_count
        self.state = self._rebuild()
        return self.state

    def redo(self) -> HandState:
        if self.cursor >= len(self.events):
            raise PokerRuleError("Aucune action ne peut être rétablie")
        self.cursor += 1
        self.state = self._rebuild()
        return self.state
