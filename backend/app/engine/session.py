from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from app.engine.holdem import HoldemEngine, PokerRuleError
from app.models import (
    ActionKind,
    ActionRequest,
    Advice,
    AnalysisLevel,
    AnteType,
    CardRequest,
    HandStatus,
    InitialProfile,
    OpponentPatch,
    PlayerConfig,
    PlayerPatch,
    PlayerReplace,
    PlayerStatus,
    SessionCreate,
    SessionState,
    ShowdownRequest,
    Street,
)
from app.opponents.model import OpponentModel
from app.strategy.advisor import StrategyAdvisor


class PokerSession:
    def __init__(self, config: SessionCreate, *, session_id: str | None = None) -> None:
        self.id = session_id or str(uuid4())
        self.name = config.session_name
        self.config = config
        self.created_at = datetime.now(UTC)
        self.updated_at = self.created_at
        self.engine = HoldemEngine(config)
        self.archived_hands: list[dict[str, Any]] = []
        self.hand_summaries: list[dict[str, Any]] = []
        self.advice_history: list[Advice] = []
        self.decision_snapshots: dict[str, dict[str, Any]] = {}
        self.current_advice: Advice | None = None
        self.advisor = StrategyAdvisor()
        self.opponents = {
            player.id: OpponentModel(
                player_id=player.id,
                name=player.name,
                initial_profile=player.initial_profile,
                custom_profile=player.custom_profile,
                notes=player.notes,
            )
            for player in config.players
            if player.id != "hero"
        }
        self.hand_opponent_baselines = {
            player_id: OpponentModel.model_validate(model.model_dump())
            for player_id, model in self.opponents.items()
        }
        hero = next(player for player in config.players if player.id == "hero")
        self.initial_hero_stack = hero.stack
        self.player_overrides: dict[str, dict[str, Any]] = {}

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> PokerSession:
        session = cls(
            SessionCreate.model_validate(payload["config"]), session_id=str(payload["id"])
        )
        session.name = str(payload["name"])
        session.created_at = datetime.fromisoformat(str(payload["created_at"]))
        session.updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        session.engine = HoldemEngine.restore(payload["engine"])
        session.archived_hands = list(payload.get("archived_hands", []))
        session.hand_summaries = list(payload.get("hand_summaries", []))
        session.advice_history = [
            Advice.model_validate(item) for item in payload.get("advice_history", [])
        ]
        session.decision_snapshots = dict(payload.get("decision_snapshots", {}))
        current_id = payload.get("current_advice_id")
        session.current_advice = next(
            (advice for advice in session.advice_history if advice.id == current_id), None
        )
        session.opponents = {
            player_id: OpponentModel.model_validate(model)
            for player_id, model in payload.get("opponents", {}).items()
        }
        baseline_payload = payload.get("hand_opponent_baselines", payload.get("opponents", {}))
        session.hand_opponent_baselines = {
            player_id: OpponentModel.model_validate(model)
            for player_id, model in baseline_payload.items()
        }
        session.initial_hero_stack = int(
            payload.get("initial_hero_stack", session.initial_hero_stack)
        )
        session.player_overrides = dict(payload.get("player_overrides", {}))
        return session

    def export(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "id": self.id,
            "name": self.name,
            "config": self.config.model_dump(mode="json"),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "engine": self.engine.export(),
            "archived_hands": self.archived_hands,
            "hand_summaries": self.hand_summaries,
            "advice_history": [advice.model_dump(mode="json") for advice in self.advice_history],
            "decision_snapshots": self.decision_snapshots,
            "current_advice_id": self.current_advice.id if self.current_advice else None,
            "opponents": {
                player_id: model.model_dump(mode="json")
                for player_id, model in self.opponents.items()
            },
            "hand_opponent_baselines": {
                player_id: model.model_dump(mode="json")
                for player_id, model in self.hand_opponent_baselines.items()
            },
            "initial_hero_stack": self.initial_hero_stack,
            "player_overrides": self.player_overrides,
        }

    @property
    def cumulative_hero_result(self) -> int:
        return sum(int(summary["hero_net"]) for summary in self.hand_summaries)

    def state(
        self,
        persistence_status: Literal["saved", "pending", "warning"] = "pending",
    ) -> SessionState:
        hand = self.engine.state.model_copy(deep=True)
        for player in hand.players:
            override = self.player_overrides.get(player.id, {})
            for key in ("name", "stack", "status", "initial_profile", "notes"):
                if key in override:
                    setattr(player, key, override[key])
            model = self.opponents.get(player.id)
            if model is not None:
                player.estimated_profile = model.estimated_profile
                player.profile_confidence = model.confidence
                player.hands_observed = model.hands_observed
        visible_advice = self.current_advice if hand.actor_id == "hero" else None
        return SessionState(
            session_id=self.id,
            session_name=self.name,
            created_at=self.created_at,
            updated_at=self.updated_at,
            config=self.config,
            hand=hand,
            advice=visible_advice,
            advice_count=len(self.advice_history),
            hands_played=len(self.hand_summaries),
            cumulative_hero_result=self.cumulative_hero_result,
            initial_hero_stack=self.initial_hero_stack,
            persistence_status=persistence_status,
        )

    def _touch(self) -> None:
        self.updated_at = datetime.now(UTC)

    def _effective_status(self, player_id: str) -> PlayerStatus:
        player = next((item for item in self.engine.state.players if item.id == player_id), None)
        if player is None:
            raise PokerRuleError("Joueur introuvable")
        value = self.player_overrides.get(player_id, {}).get("status", player.status)
        return value if isinstance(value, PlayerStatus) else PlayerStatus(str(value))

    def _unavailable_for_current_hand(self, player_id: str) -> bool:
        override = self.player_overrides.get(player_id, {})
        status = override.get("status")
        return bool(override.get("pending_join")) or status in {
            PlayerStatus.ABSENT,
            PlayerStatus.ELIMINATED,
            "absent",
            "eliminated",
        }

    def _skip_unavailable_actors(self) -> bool:
        """Couche automatiquement un siège retiré lorsqu'il arrive à la parole."""
        changed = False
        while (
            self.engine.state.status == HandStatus.ACTIVE
            and self.engine.state.actor_id is not None
            and self._unavailable_for_current_hand(self.engine.state.actor_id)
        ):
            self.engine.take_action(ActionRequest(action=ActionKind.FOLD))
            changed = True
        return changed

    def take_action(self, request: ActionRequest) -> None:
        actor_id = self.engine.state.actor_id
        if actor_id is None:
            raise PokerRuleError("Aucun joueur ne doit agir")
        self.engine.take_action(request)
        self._skip_unavailable_actors()
        self._rebuild_current_opponents()
        if actor_id == "hero":
            self._record_actual_action(request)
        self.current_advice = None
        self._sync_completion()
        self._touch()

    def set_card(self, request: CardRequest) -> None:
        self.engine.set_card(request.slot, request.card)
        if self._skip_unavailable_actors():
            self._rebuild_current_opponents()
            self._sync_completion()
        self.current_advice = None
        self._touch()

    def clear_card(self, slot: str) -> None:
        self.engine.clear_card(slot)
        self.current_advice = None
        self._touch()

    def settle_showdown(self, request: ShowdownRequest) -> None:
        self.engine.settle_showdown(request)
        self._rebuild_current_opponents()
        self._sync_completion()
        self.current_advice = None
        self._touch()

    def undo(self) -> None:
        was_complete = self.engine.state.status == HandStatus.COMPLETE
        self.engine.undo()
        self._skip_unavailable_actors()
        self._rebuild_current_opponents()
        if was_complete and self.engine.state.status != HandStatus.COMPLETE:
            self._remove_current_summary()
        self._reconcile_advice_after_rewind()
        self.current_advice = None
        self._touch()

    def _reconcile_advice_after_rewind(self) -> None:
        if self.engine.state.actor_id != "hero":
            return
        latest = next(
            (
                advice
                for advice in reversed(self.advice_history)
                if advice.hand_id == self.engine.state.id and advice.actual_action is not None
            ),
            None,
        )
        if latest is not None:
            latest.actual_action = None
            latest.actual_amount = None
            latest.ev_difference = None

    def redo(self) -> None:
        self.engine.redo()
        self._skip_unavailable_actors()
        self._rebuild_current_opponents()
        self._sync_completion()
        self.current_advice = None
        self._touch()

    def restart_hand(self) -> None:
        """Remet la main en cours à son état initial (comme si elle venait de commencer).

        Conserve les mêmes joueurs, tapis de début de main, bouton, blindes/antes
        et numéro de main; supprime toute carte et toute action volontaire. Purge
        aussi les traces de la main annulée: résumé de main, historique de
        conseils et instantanés de décision associés, puis restaure les modèles
        adverses à leur état de début de main pour ne pas polluer l'apprentissage
        avec des actions désormais inexistantes.
        """
        was_complete = self.engine.state.status == HandStatus.COMPLETE
        current_hand_id = self.engine.state.id
        self.engine.restart_hand()
        self._skip_unavailable_actors()
        self._rebuild_current_opponents()
        if was_complete:
            self._remove_current_summary()
        removed_ids = [
            advice.id for advice in self.advice_history if advice.hand_id == current_hand_id
        ]
        self.advice_history = [
            advice for advice in self.advice_history if advice.hand_id != current_hand_id
        ]
        for advice_id in removed_ids:
            self.decision_snapshots.pop(advice_id, None)
        self.current_advice = None
        self._touch()

    def generate_advice(
        self,
        *,
        level: AnalysisLevel = AnalysisLevel.FAST,
        trials: int | None = None,
        seed: int | None = None,
    ) -> Advice:
        advice = self.advisor.advise(
            session_id=self.id,
            config=self.config,
            state=self.engine.state,
            opponents=self.opponents,
            level=level,
            trials=trials,
            seed=seed,
        )
        self.advice_history.append(advice)
        self.decision_snapshots[advice.id] = self.decision_snapshot()
        self.current_advice = advice
        self._touch()
        return advice

    def decision_snapshot(self) -> dict[str, Any]:
        return {
            **self.engine.export(),
            "history_context": self.history_context(self.engine),
            "opponents_at_decision": {
                player_id: model.model_dump(mode="json")
                for player_id, model in self.opponents.items()
            },
        }

    @staticmethod
    def history_context(engine: HoldemEngine) -> dict[str, Any]:
        """Fige les champs légers nécessaires à la liste d'historique.

        Le replay event-sourcé complet reste dans l'instantané, mais la liste
        de plusieurs milliers de décisions ne doit pas le reconstruire ligne
        par ligne. Les anciens instantanés sans ce contexte restent lisibles
        grâce au chemin de compatibilité de la présentation.
        """

        state = engine.state
        hero = next(player for player in state.players if player.id == "hero")
        previous = next(
            (
                event
                for event in reversed(state.events)
                if event.type.value == "action" and event.actor_id != "hero"
            ),
            None,
        )
        opponent_ids = [
            player.id
            for player in state.players
            if player.id != "hero"
            and player.status
            not in {PlayerStatus.FOLDED, PlayerStatus.ABSENT, PlayerStatus.ELIMINATED}
        ]
        return {
            "hand_number": state.number,
            "unit": engine.config.unit.value,
            "big_blind": engine.config.big_blind,
            "hero_position": hero.position,
            "hero_cards": list(state.hero_cards),
            "board": list(state.board),
            "preceding_action": (
                previous.action.value if previous is not None and previous.action else None
            ),
            "opponent_ids": opponent_ids,
        }

    def opponents_from_snapshot(self, snapshot: dict[str, Any]) -> dict[str, OpponentModel]:
        saved = snapshot.get("opponents_at_decision")
        if not isinstance(saved, dict):
            return {
                player_id: OpponentModel.model_validate(model.model_dump())
                for player_id, model in self.opponents.items()
            }
        return {
            str(player_id): OpponentModel.model_validate(payload)
            for player_id, payload in saved.items()
        }

    def expert_analysis(
        self, advice_id: str, *, trials: int = 15_000, seed: int | None = None
    ) -> Advice:
        snapshot = self.decision_snapshots.get(advice_id)
        if snapshot is None:
            raise PokerRuleError("Instantané de décision introuvable")
        engine = HoldemEngine.restore(snapshot)
        return self.advisor.advise(
            session_id=self.id,
            config=self.config,
            state=engine.state,
            opponents=self.opponents_from_snapshot(snapshot),
            level=AnalysisLevel.EXPERT,
            trials=trials,
            seed=seed,
        )

    def _record_actual_action(self, request: ActionRequest) -> None:
        advice = next(
            (
                item
                for item in reversed(self.advice_history)
                if item.hand_id == self.engine.state.id and item.actual_action is None
            ),
            None,
        )
        if advice is None:
            return
        matching = [item for item in advice.alternatives if item.action == request.action]
        if matching:
            actual = min(
                matching,
                key=lambda item: abs((item.amount or 0) - (request.amount or item.amount or 0)),
            )
            best_ev = max(item.guarded_ev for item in advice.alternatives)
            advice.ev_difference = best_ev - actual.guarded_ev
        advice.actual_action = request.action
        advice.actual_amount = request.amount

    def _sync_completion(self) -> None:
        result = self.engine.state.result
        if self.engine.state.status != HandStatus.COMPLETE or result is None:
            return
        if any(summary["hand_id"] == self.engine.state.id for summary in self.hand_summaries):
            return
        hero_net = result.net_results.get("hero", 0)
        summary = {
            "hand_id": self.engine.state.id,
            "hand_number": self.engine.state.number,
            "status": result.status,
            "winners": result.winners,
            "total_pot": result.total_pot,
            "hero_net": hero_net,
            "hero_received": result.received.get("hero", 0),
            "hero_stack": next(
                player.stack for player in self.engine.state.players if player.id == "hero"
            ),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        self.hand_summaries.append(summary)
        for advice in self.advice_history:
            if advice.hand_id == self.engine.state.id:
                advice.result_net = hero_net

    def _remove_current_summary(self) -> None:
        self.hand_summaries = [
            summary for summary in self.hand_summaries if summary["hand_id"] != self.engine.state.id
        ]
        for advice in self.advice_history:
            if advice.hand_id == self.engine.state.id:
                advice.result_net = None

    def next_hand(self) -> None:
        if self.engine.state.status != HandStatus.COMPLETE:
            raise PokerRuleError(
                "La main en cours doit être terminée avant de passer à la suivante"
            )
        self.archived_hands.append(self.engine.export())
        self.hand_opponent_baselines = {
            player_id: OpponentModel.model_validate(model.model_dump())
            for player_id, model in self.opponents.items()
        }
        current_players = sorted(self.engine.state.players, key=lambda player: player.seat)
        eligible = []
        for player in current_players:
            override = self.player_overrides.get(player.id, {})
            effective_stack = int(override.get("stack", player.stack))
            effective_status = override.get("status", player.status)
            if effective_stack > 0 and effective_status not in {
                PlayerStatus.ABSENT,
                PlayerStatus.ELIMINATED,
                "absent",
                "eliminated",
            }:
                eligible.append(player)
        if len(eligible) < 2:
            raise PokerRuleError("La session ne contient plus deux joueurs capables de jouer")
        old_button_index = next(
            index
            for index, player in enumerate(current_players)
            if player.id == self.engine.state.button_player_id
        )
        button = None
        for offset in range(1, len(current_players) + 1):
            candidate = current_players[(old_button_index + offset) % len(current_players)]
            if candidate in eligible:
                button = candidate.id
                break
        if button is None:
            raise PokerRuleError("Impossible de faire tourner le bouton")
        next_number = self.engine.hand_number + 1
        small_blind = self.config.small_blind
        big_blind = self.config.big_blind
        if self.config.mode.value == "tournament" and self.config.blind_levels:
            elapsed_minutes = (datetime.now(UTC) - self.created_at).total_seconds() / 60
            applicable = [
                level
                for level in self.config.blind_levels
                if (level.after_hands is not None and next_number - 1 >= level.after_hands)
                or (level.after_minutes is not None and elapsed_minutes >= level.after_minutes)
            ]
            if applicable:
                level = applicable[-1]
                small_blind = level.small_blind
                big_blind = level.big_blind
                ante_type = self.config.ante_type
                if level.ante > 0 and ante_type == AnteType.NONE:
                    ante_type = AnteType.CLASSIC
                self.config = self.config.model_copy(
                    update={"ante": level.ante, "ante_type": ante_type}
                )
        elif (
            self.config.mode.value == "tournament"
            and self.config.blind_increase_every_hands
            and (next_number - 1) % self.config.blind_increase_every_hands == 0
        ):
            small_blind = max(
                small_blind + 1, round(small_blind * self.config.blind_increase_factor)
            )
            big_blind = max(big_blind + 1, round(big_blind * self.config.blind_increase_factor))
        configs: list[PlayerConfig] = []
        old_configs = {player.id: player for player in self.config.players}
        for player in current_players:
            original = old_configs[player.id]
            override = self.player_overrides.get(player.id, {})
            stack = int(override.get("stack", player.stack))
            status = override.get("status")
            if status is None:
                if original.status == PlayerStatus.ABSENT:
                    status = PlayerStatus.ABSENT
                elif stack <= 0:
                    status = PlayerStatus.ELIMINATED
                else:
                    status = PlayerStatus.ACTIVE
            configs.append(
                PlayerConfig(
                    id=player.id,
                    name=str(override.get("name", player.name)),
                    seat=player.seat,
                    stack=stack,
                    status=status,
                    initial_profile=override.get("initial_profile", original.initial_profile),
                    notes=str(override.get("notes", player.notes)),
                    custom_profile=original.custom_profile,
                )
            )
        self.config = self.config.model_copy(
            update={
                "players": configs,
                "button_player_id": button,
                "small_blind_player_id": None,
                "big_blind_player_id": None,
                "small_blind": small_blind,
                "big_blind": big_blind,
            }
        )
        self.engine = HoldemEngine(
            self.config,
            hand_number=next_number,
            button_player_id=button,
            players=configs,
        )
        self.player_overrides = {}
        self.current_advice = None
        self._touch()

    def _rebuild_current_opponents(self) -> None:
        self.opponents = {
            player_id: OpponentModel.model_validate(model.model_dump())
            for player_id, model in self.hand_opponent_baselines.items()
        }
        state = self.engine.state
        positions = {player.id: player.position for player in state.players}
        for event in state.events:
            if (
                event.type.value == "action"
                and event.actor_id in self.opponents
                and event.action is not None
            ):
                model = self.opponents[event.actor_id]
                model.observe_action(
                    hand_id=state.id,
                    street=Street(event.payload.get("street", "preflop")),
                    action=ActionKind(event.payload.get("resolved_action", event.action.value)),
                    position=str(event.payload.get("position", positions[event.actor_id])),
                    amount=event.amount or 0,
                    pot_before=int(event.payload.get("pot_before", 0)),
                    facing_raise=bool(event.payload.get("facing_raise", False)),
                    raise_count=int(event.payload.get("raise_count", 0)),
                    facing_cbet=bool(event.payload.get("facing_cbet", False)),
                    is_cbet=bool(event.payload.get("is_cbet", False)),
                    cbet_opportunity=bool(event.payload.get("cbet_opportunity", False)),
                )
        result = state.result
        if result is not None:
            for player_id, cards in state.revealed_hands.items():
                showdown_model = self.opponents.get(player_id)
                if showdown_model is None or len(cards) != 2:
                    continue
                won = any(player_id in pot.winner_ids for pot in result.pots)
                aggressive = any(
                    event.actor_id == player_id
                    and event.payload.get(
                        "resolved_action", event.action.value if event.action else ""
                    )
                    in {ActionKind.BET.value, ActionKind.RAISE.value}
                    for event in state.events
                )
                bluff = aggressive and result.hand_ranks.get(player_id) == "carte haute"
                showdown_model.observe_showdown(won=won, bluff=bluff)

    def patch_player(self, player_id: str, patch: PlayerPatch) -> None:
        player = next((item for item in self.engine.state.players if item.id == player_id), None)
        if player is None:
            raise PokerRuleError("Joueur introuvable")
        changes = patch.model_dump(exclude_none=True)
        if player_id == "hero" and "name" in changes:
            raise PokerRuleError("Le nom Ryanchl n'est pas modifiable")

        displayed_name = str(self.player_overrides.get(player_id, {}).get("name", player.name))
        if changes.get("name") == displayed_name:
            changes.pop("name", None)
        if "stack" in changes:
            requested_stack = int(changes.pop("stack"))
            self.engine.adjust_stack(player_id, requested_stack)
            player = next(item for item in self.engine.state.players if item.id == player_id)
        if "status" in changes:
            requested_status = changes.pop("status")
            requested_status = (
                requested_status
                if isinstance(requested_status, PlayerStatus)
                else PlayerStatus(str(requested_status))
            )
            if requested_status != self._effective_status(player_id):
                if requested_status in {PlayerStatus.ABSENT, PlayerStatus.ELIMINATED}:
                    self.remove_player(player_id, status=requested_status)
                else:
                    raise PokerRuleError(
                        "Utilisez le bouton + du siège pour faire entrer un joueur "
                        "à la prochaine main"
                    )
        if changes:
            self.player_overrides.setdefault(player_id, {}).update(changes)
        self.current_advice = None
        self._touch()

    def remove_player(self, player_id: str, *, status: PlayerStatus = PlayerStatus.ABSENT) -> None:
        if player_id == "hero":
            raise PokerRuleError("Ryanchl ne peut pas être retiré de sa propre table")
        player = next((item for item in self.engine.state.players if item.id == player_id), None)
        if player is None:
            raise PokerRuleError("Joueur introuvable")
        if self.engine.state.status == HandStatus.SHOWDOWN:
            raise PokerRuleError("Terminez le showdown avant de retirer ce joueur")
        if player.status == PlayerStatus.ALL_IN and self.engine.state.status != HandStatus.COMPLETE:
            raise PokerRuleError("Un joueur à tapis ne peut quitter la table qu'après cette main")
        seated = [
            item
            for item in self.engine.state.players
            if self._effective_status(item.id) not in {PlayerStatus.ABSENT, PlayerStatus.ELIMINATED}
        ]
        if player in seated and len(seated) <= 2:
            raise PokerRuleError("La table doit conserver au moins deux joueurs assis")
        self.player_overrides.setdefault(player_id, {}).update(
            {"status": status, "pending_join": False}
        )
        if self._skip_unavailable_actors():
            self._rebuild_current_opponents()
            self._sync_completion()
        self.current_advice = None
        self._touch()

    def seat_player(self, player_id: str, payload: PlayerReplace) -> None:
        if player_id == "hero":
            raise PokerRuleError("Le siège de Ryanchl est déjà réservé")
        if self._effective_status(player_id) not in {
            PlayerStatus.ABSENT,
            PlayerStatus.ELIMINATED,
        }:
            raise PokerRuleError("Ce siège est déjà occupé")
        self.replace_player(player_id, payload)
        self.player_overrides.setdefault(player_id, {}).update(
            {"status": PlayerStatus.ACTIVE, "pending_join": True}
        )
        if self._skip_unavailable_actors():
            self._rebuild_current_opponents()
            self._sync_completion()
        self.current_advice = None
        self._touch()

    def replace_player(self, player_id: str, payload: PlayerReplace) -> None:
        """Fait entrer un nouveau joueur au siège d'un joueur existant.

        L'identifiant interne ne change pas: le journal d'événements du moteur y
        fait référence. Le remplacement agit au niveau session, via les mêmes
        surcharges (`player_overrides`) que `patch_player`, avec la même
        validation de tapis. Si le joueur remplacé était engagé dans la main en
        cours, le nouveau joueur hérite tel quel de sa situation (mises,
        statut couché/à tapis): seul son nom affiché change immédiatement. Le
        modèle adverse est recréé de zéro (aucune main observée).
        """
        if player_id == "hero":
            raise PokerRuleError("Le joueur principal ne peut pas être remplacé")
        player = next((item for item in self.engine.state.players if item.id == player_id), None)
        if player is None:
            raise PokerRuleError("Joueur introuvable")
        name = payload.name.strip()
        if not name:
            raise PokerRuleError("Le nom du nouveau joueur ne peut pas être vide")
        other_names = {
            str(self.player_overrides.get(other.id, {}).get("name", other.name)).casefold()
            for other in self.engine.state.players
            if other.id != player_id
        }
        if name.casefold() in other_names:
            raise PokerRuleError("Ce nom est déjà utilisé par un autre joueur de la table")
        profile = payload.initial_profile or InitialProfile.UNKNOWN
        current_status = self._effective_status(player_id)
        joining_empty_seat = current_status in {
            PlayerStatus.ABSENT,
            PlayerStatus.ELIMINATED,
        }
        changes: dict[str, Any] = {"name": name, "initial_profile": profile}
        if payload.stack is not None:
            if joining_empty_seat:
                if payload.stack <= 0:
                    raise PokerRuleError("Le nouveau joueur doit posséder un tapis positif")
                changes["stack"] = payload.stack
            else:
                if payload.stack < player.total_contribution:
                    raise PokerRuleError(
                        "Le nouveau tapis ne peut pas être inférieur aux jetons déjà engagés"
                    )
                self.engine.adjust_stack(player_id, payload.stack)
        self.player_overrides.setdefault(player_id, {}).update(changes)
        if self.engine.cursor == self.engine.forced_count:
            configs = [item.model_copy(deep=True) for item in self.engine.initial_players]
            target = next(item for item in configs if item.id == player_id)
            for key, value in changes.items():
                setattr(target, key, value)
            self.config = self.config.model_copy(update={"players": configs})
            self.engine = HoldemEngine(
                self.config,
                hand_number=self.engine.hand_number,
                hand_id=self.engine.hand_id,
                button_player_id=self.engine.button_player_id,
                players=configs,
            )
        fresh_model = OpponentModel(
            player_id=player_id,
            name=name,
            initial_profile=profile,
            custom_profile=payload.custom_profile,
        )
        self.opponents[player_id] = fresh_model
        self.hand_opponent_baselines[player_id] = OpponentModel.model_validate(
            fresh_model.model_dump()
        )
        self.current_advice = None
        self._touch()

    def patch_opponent(self, player_id: str, patch: OpponentPatch) -> OpponentModel:
        baseline = self.hand_opponent_baselines.get(player_id)
        if baseline is None:
            raise PokerRuleError("Profil adverse introuvable")
        changes = patch.model_dump(exclude_none=True)
        if "adaptation_enabled" in changes:
            changes["exploit_enabled"] = changes.pop("adaptation_enabled")
        for key, value in changes.items():
            setattr(baseline, key, value)
        baseline.last_updated = datetime.now(UTC)
        self._rebuild_current_opponents()
        self.current_advice = None
        self._touch()
        return self.opponents[player_id]

    def reset_opponent(self, player_id: str) -> OpponentModel:
        old = self.hand_opponent_baselines.get(player_id)
        if old is None:
            raise PokerRuleError("Profil adverse introuvable")
        reset = OpponentModel(
            player_id=old.player_id,
            name=old.name,
            initial_profile=old.initial_profile,
            custom_profile=old.custom_profile,
            notes=old.notes,
            exploit_enabled=old.exploit_enabled,
        )
        self.hand_opponent_baselines[player_id] = reset
        self._rebuild_current_opponents()
        self.current_advice = None
        self._touch()
        return self.opponents[player_id]

    def merge_opponents(self, source_id: str, target_id: str) -> OpponentModel:
        source = self.hand_opponent_baselines.get(source_id)
        target = self.hand_opponent_baselines.get(target_id)
        if source is None or target is None:
            raise PokerRuleError("Un des profils à fusionner est introuvable")
        target.merge(source)
        self._rebuild_current_opponents()
        self.current_advice = None
        self._touch()
        return self.opponents[target_id]

    def import_opponent(self, model: OpponentModel) -> OpponentModel:
        if model.player_id not in self.hand_opponent_baselines:
            raise PokerRuleError("Ce joueur n'existe pas dans la session")
        imported = OpponentModel.model_validate(model.model_dump())
        self.hand_opponent_baselines[model.player_id] = imported
        self._rebuild_current_opponents()
        self.current_advice = None
        self._touch()
        return self.opponents[model.player_id]

    def session_summary(self) -> dict[str, Any]:
        hero = next(player for player in self.engine.state.players if player.id == "hero")
        won = sum(summary["hero_net"] > 0 for summary in self.hand_summaries)
        lost = sum(summary["hero_net"] < 0 for summary in self.hand_summaries)
        split = sum(summary["status"] == "split" for summary in self.hand_summaries)
        no_showdown = sum(
            summary["status"] == "won_without_showdown" for summary in self.hand_summaries
        )
        positive = [
            int(summary.get("hero_received", summary["hero_net"]))
            for summary in self.hand_summaries
            if summary["hero_net"] > 0
        ]
        negative = [
            int(summary.get("total_pot", abs(summary["hero_net"])))
            for summary in self.hand_summaries
            if summary["hero_net"] < 0
        ]
        return {
            "session_id": self.id,
            "session_name": self.name,
            "hands_played": len(self.hand_summaries),
            "initial_hero_stack": self.initial_hero_stack,
            "final_hero_stack": hero.stack,
            "net_result": self.cumulative_hero_result,
            "net_result_big_blinds": self.cumulative_hero_result / self.config.big_blind,
            "hands_won": won,
            "hands_lost": lost,
            "split_pots": split,
            "wins_without_showdown": no_showdown,
            "showdown_wins": won - no_showdown,
            "biggest_pot_won": max(positive, default=0),
            "biggest_pot_lost": max(negative, default=0),
            "advice_count": len(self.advice_history),
        }
