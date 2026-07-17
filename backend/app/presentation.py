from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

from app.engine.holdem import HoldemEngine
from app.engine.session import PokerSession
from app.models import ActionKind, Advice, HandState, HandStatus, PlayerStatus, Street
from app.opponents.model import OpponentModel

ACTION_LABELS = {
    ActionKind.FOLD: "Fold",
    ActionKind.CHECK: "Check",
    ActionKind.CALL: "Call",
    ActionKind.BET: "Raise",
    ActionKind.RAISE: "Raise",
    ActionKind.ALL_IN: "All-in",
}


def _frontend_profile(value: str) -> str:
    return {"tight_aggressive": "tag", "loose_aggressive": "lag"}.get(value, value)


def _street(street: Street) -> str:
    return "terminee" if street == Street.COMPLETE else street.value


def _session_config_view(session: PokerSession) -> dict[str, Any]:
    """Expose les réglages persistés dans le contrat utilisé par le frontend.

    Les montants internes restent des jetons entiers. Les euros fictifs et les
    grosses blindes sont donc reconvertis vers l'unité saisie avant d'être
    remis dans le formulaire lors d'une reprise de session.
    """

    config = session.config
    scale = 100 if config.unit.value in {"fictional_euros", "big_blinds"} else 1

    def display_amount(value: int) -> float | int:
        converted = value / scale
        return int(converted) if converted.is_integer() else converted

    levels = [
        {
            "after_hands": level.after_hands,
            "small_blind": display_amount(level.small_blind),
            "big_blind": display_amount(level.big_blind),
            "ante": display_amount(level.ante),
        }
        for level in config.blind_levels
        if level.after_hands is not None
    ]
    return {
        "player_count": len(config.players),
        "players": [
            {
                "id": player.id,
                "name": "Ryanchl" if player.id == "hero" else player.name,
                "seat": player.seat,
                "stack": display_amount(player.stack),
                "initial_profile": _frontend_profile(player.initial_profile.value),
                **({"custom_profile": player.custom_profile} if player.custom_profile else {}),
            }
            for player in config.players
        ],
        "unit": config.unit.value,
        "small_blind": display_amount(config.small_blind),
        "big_blind": display_amount(config.big_blind),
        "ante": display_amount(config.ante),
        "ante_type": "big_blind_ante" if config.ante_type.value == "big_blind" else "classic",
        "game_mode": config.mode.value,
        "dealer_id": config.button_player_id,
        "small_blind_id": config.small_blind_player_id or config.button_player_id,
        "big_blind_id": config.big_blind_player_id or config.button_player_id,
        "blind_levels": levels,
        "advice_mode": "quiz" if config.quiz_mode else "immediate",
    }


def advice_view(advice: Advice) -> dict[str, Any]:
    def option(item: Any) -> dict[str, Any]:
        return {
            "action": item.action.value,
            "label": ACTION_LABELS[item.action],
            "amount": item.amount,
            "frequency": item.frequency,
            "ev": item.guarded_ev,
        }

    def section(action: ActionKind, mode: str) -> dict[str, Any]:
        candidates = [item for item in advice.alternatives if item.action == action]
        candidate = max(
            candidates,
            key=(
                (lambda item: item.balanced_ev)
                if mode == "balanced"
                else (lambda item: item.exploit_ev)
                if mode == "exploit"
                else (lambda item: item.guarded_ev)
            ),
        )
        return {
            "headline": ACTION_LABELS[action],
            "action": action.value,
            "amount": candidate.amount,
            "confidence": advice.confidence,
            "source": "precomputed"
            if advice.precision == "deterministic_table_abstraction"
            else "simulation",
            "is_exact": False,
            "explanation": advice.detailed_explanation or advice.explanation,
            "options": [option(item) for item in advice.alternatives],
        }

    robust = max(advice.alternatives, key=lambda item: item.guarded_ev)
    return {
        "id": advice.id,
        "hand_id": advice.hand_id,
        "street": _street(advice.street),
        "balanced": section(advice.balanced_action, "balanced"),
        "exploitative": section(advice.exploit_action, "exploit"),
        "final": section(advice.primary_action, "final"),
        "robust_action": option(robust),
        "pot_odds": advice.pot_odds,
        "minimum_equity": advice.equity_required,
        "estimated_equity": advice.equity,
        "spr": advice.spr,
        "effective_stack": advice.effective_stack,
        "limitations": advice.limitations,
        "explanation_pending": advice.explanation_pending,
    }


def _summary(session: PokerSession, state: HandState) -> dict[str, Any] | None:
    result = state.result
    if result is None:
        return None
    hero = next(player for player in state.players if player.id == "hero")
    players = []
    for player in state.players:
        entry: dict[str, Any] = {
            "player_id": player.id,
            "name": player.name,
            "received": result.received.get(player.id, 0),
            "net": result.net_results.get(player.id, -player.total_contribution),
        }
        if player.id == "hero" and len(state.hero_cards) == 2:
            entry["revealed_cards"] = state.hero_cards
        elif player.id in state.revealed_hands:
            entry["revealed_cards"] = state.revealed_hands[player.id]
        if player.id in result.best_five:
            entry["best_five"] = result.best_five[player.id]
            entry["hand_name"] = result.hand_ranks[player.id]
        players.append(entry)
    hero_received = result.received.get("hero", 0)
    hero_net = result.net_results.get("hero", 0)
    advice = next(
        (item for item in reversed(session.advice_history) if item.hand_id == state.id), None
    )
    return {
        "status": result.status,
        "winners": result.winners,
        "total_pot": result.total_pot,
        "hero_contribution": hero.total_contribution,
        "hero_received": hero_received,
        "hero_net": hero_net,
        "hero_net_bb": hero_net / session.config.big_blind,
        "hero_new_stack": hero.stack,
        "session_net": session.cumulative_hero_result,
        "players": players,
        "pots": [pot.model_dump(mode="json") for pot in result.pots],
        "principal_advice": ACTION_LABELS[advice.primary_action] if advice else None,
        "hero_action": ACTION_LABELS[advice.actual_action]
        if advice and advice.actual_action
        else None,
        "advice_difference": (
            f"Écart d'EV estimé : {advice.ev_difference:.2f} jetons"
            if advice and advice.ev_difference is not None
            else None
        ),
    }


def table_state_view(
    session: PokerSession,
    *,
    state: HandState | None = None,
    current_advice: Advice | None | bool = False,
    persistence_status: str = "pending",
    opponents: dict[str, OpponentModel] | None = None,
    big_blind: int | None = None,
) -> dict[str, Any]:
    hand = state or session.engine.state
    visible_opponents = session.opponents if opponents is None else opponents
    blind_scale = session.config.big_blind if big_blind is None else big_blind
    call_descriptor = next(
        (item for item in hand.legal_actions if item.action == ActionKind.CALL and item.enabled),
        None,
    )
    to_call = call_descriptor.to_call if call_descriptor else 0
    phase = {
        HandStatus.ACTIVE: "playing",
        HandStatus.AWAITING_CARDS: "awaiting_cards",
        HandStatus.SHOWDOWN: "showdown",
        HandStatus.COMPLETE: "summary",
    }[hand.status]
    action_log = []
    # Les remplacements de joueur effectués pendant une main vivent dans
    # player_overrides tant que le moteur n'est pas reconstruit: la vue doit
    # afficher le nom du joueur actuellement assis, pas celui du journal.
    names = {
        player.id: str(session.player_overrides.get(player.id, {}).get("name", player.name))
        for player in hand.players
    }
    running_pot = 0
    for event in hand.events:
        if event.amount:
            running_pot += event.amount
        if event.type.value != "action" or event.actor_id is None or event.action is None:
            continue
        action_log.append(
            {
                "id": event.id,
                "sequence": event.sequence,
                "player_id": event.actor_id,
                "player_name": names[event.actor_id],
                "street": event.payload.get("street", _street(hand.street)),
                "action": event.action.value,
                "amount": event.amount or 0,
                "pot_after": event.payload.get("pot_before", running_pot - (event.amount or 0))
                + (event.amount or 0),
                "created_at": event.created_at,
            }
        )
    player_views = []
    for player in hand.players:
        model = visible_opponents.get(player.id)
        override = session.player_overrides.get(player.id, {})
        pending_join = bool(override.get("pending_join"))
        initial_profile = override.get("initial_profile", player.initial_profile)
        profile = {
            "initial": _frontend_profile(
                initial_profile.value if hasattr(initial_profile, "value") else str(initial_profile)
            ),
            "estimated": model.estimated_profile if model else "joueur_principal",
            "confidence": model.confidence if model else 1.0,
            "hands_observed": model.hands_observed if model else len(session.hand_summaries),
            "adaptation_enabled": model.exploit_enabled if model else False,
        }
        override_status = override.get("status")
        if pending_join or override_status in {PlayerStatus.ABSENT, "absent"}:
            status = "away"
        elif override_status in {PlayerStatus.ELIMINATED, "eliminated"}:
            status = "eliminated"
        else:
            status = "away" if player.status == PlayerStatus.ABSENT else player.status.value
        visible_stack = int(override.get("stack", player.stack)) if pending_join else player.stack
        player_views.append(
            {
                "id": player.id,
                "name": names[player.id],
                "seat": player.seat,
                "position": player.position,
                "stack": visible_stack,
                "stack_bb": visible_stack / blind_scale,
                "street_bet": player.street_contribution,
                "total_contribution": player.total_contribution,
                "last_action": player.last_action,
                "status": status,
                "pending_join": pending_join,
                "is_dealer": player.id == hand.button_player_id,
                "is_small_blind": player.id == hand.small_blind_player_id,
                "is_big_blind": player.id == hand.big_blind_player_id,
                "profile": profile,
            }
        )
    legal = [
        {
            "action": item.action.value,
            "enabled": item.enabled,
            "reason": item.reason,
            "min_amount": item.min_total,
            "max_amount": item.max_total,
            "call_amount": item.to_call,
            "all_in_call": item.is_all_in_only and item.action == ActionKind.CALL,
        }
        for item in hand.legal_actions
    ]
    required = [slot for slot in ("hero_1", "hero_2") if slot not in hand.selected_cards]
    required.extend(hand.awaiting_slots)
    advice = session.current_advice if current_advice is False else current_advice
    visible_advice = advice if isinstance(advice, Advice) and hand.actor_id == "hero" else None
    showdown_ids = [
        player.id
        for player in hand.players
        if player.status not in {PlayerStatus.FOLDED, PlayerStatus.ABSENT, PlayerStatus.ELIMINATED}
    ]
    return {
        "session_id": session.id,
        "config": _session_config_view(session),
        "hand": {
            "id": hand.id,
            "number": hand.number,
            "unit": session.config.unit.value,
            "small_blind": session.config.small_blind,
            "big_blind": blind_scale,
            "ante": session.config.ante,
            "street": _street(hand.street),
            "phase": phase,
            "pot": hand.pot,
            "side_pots": [pot.model_dump(mode="json") for pot in hand.pots],
            "to_call": to_call,
            "current_bet": hand.current_bet,
            "last_full_raise": hand.last_full_raise,
            "active_player_id": hand.actor_id,
            "players_remaining": len(
                [
                    player
                    for player in player_views
                    if player["status"] not in {"folded", "away", "eliminated"}
                ]
            ),
            "board": hand.board,
            "hero_cards": hand.hero_cards,
            "action_log": action_log,
            "showdown_player_ids": showdown_ids if hand.status == HandStatus.SHOWDOWN else None,
            "summary": _summary(session, hand),
        },
        "players": player_views,
        "legal_actions": legal,
        "selector": {"next_slot": required[0] if required else None, "required_slots": required},
        "advice": advice_view(visible_advice) if visible_advice else None,
        "persistence_status": {"saved": "saved", "pending": "saving", "warning": "error"}[
            persistence_status
        ],
    }


def history_decision_view(session: PokerSession, advice: Advice) -> dict[str, Any]:
    snapshot = session.decision_snapshots.get(advice.id)
    context = snapshot.get("history_context") if snapshot else None
    if not isinstance(context, dict):
        engine = HoldemEngine.restore(snapshot) if snapshot else session.engine
        context = PokerSession.history_context(engine)
    difference = advice.ev_difference or 0.0
    big_blind = int(context["big_blind"])
    scale = max(1.0, big_blind)
    quality = (
        "excellent"
        if difference <= 0.02 * scale
        else "acceptable"
        if difference <= 0.10 * scale
        else "questionable"
        if difference <= 0.30 * scale
        else "mistake"
    )
    preceding = context.get("preceding_action")
    preceding_action = ActionKind(str(preceding)) if preceding else None
    return {
        "id": advice.id,
        "hand_id": advice.hand_id,
        "hand_number": int(context["hand_number"]),
        "unit": str(context["unit"]),
        "big_blind": big_blind,
        "date": advice.created_at,
        "street": _street(advice.street),
        "position": str(context["hero_position"]),
        "hero_cards": list(context["hero_cards"]),
        "board": list(context["board"]),
        "preceding_action": preceding_action.value if preceding_action else "Aucune",
        "balanced_advice": ACTION_LABELS[advice.balanced_action],
        "exploitative_advice": ACTION_LABELS[advice.exploit_action],
        "final_advice": ACTION_LABELS[advice.primary_action],
        "recommended_amount": advice.recommended_total,
        "chosen_action": ACTION_LABELS[advice.actual_action]
        if advice.actual_action
        else "Non renseignée",
        "ev_difference": difference,
        "hand_result": advice.result_net or 0,
        "quality": quality,
        "confidence": advice.confidence,
        "opponent_ids": list(context["opponent_ids"]),
        "effective_stack_bb": advice.effective_stack / big_blind,
        "short_explanation": advice.explanation,
    }


def _decision_replay_steps(
    session: PokerSession,
    advice: Advice,
    snapshot: dict[str, Any],
    opponents: dict[str, OpponentModel],
) -> list[dict[str, Any]]:
    """Reconstruit les états réellement disponibles jusqu'à la décision.

    Le journal étant event-sourcé, chaque curseur produit un état complet sans
    injecter les cartes adverses révélées plus tard. La dernière étape porte le
    conseil figé correspondant à la décision consultée.
    """

    forced_count = int(snapshot["forced_count"])
    final_cursor = int(snapshot["cursor"])
    events = snapshot["events"]
    slot_labels = {
        "hero_1": "première carte de Ryanchl",
        "hero_2": "deuxième carte de Ryanchl",
        "flop_1": "première carte du flop",
        "flop_2": "deuxième carte du flop",
        "flop_3": "troisième carte du flop",
        "turn": "turn",
        "river": "river",
    }
    steps: list[dict[str, Any]] = []
    for cursor in range(forced_count, final_cursor + 1):
        payload = deepcopy(snapshot)
        payload["cursor"] = cursor
        engine = HoldemEngine.restore(payload)
        state_view = table_state_view(
            session,
            state=engine.state,
            current_advice=None,
            persistence_status="saved",
            opponents=opponents,
            big_blind=engine.config.big_blind,
        )
        event = events[cursor - 1] if cursor > forced_count else None
        event_type = "initial"
        label = "Blindes et antes posées"
        action = None
        actor_id = None
        actor_name = None
        amount = None
        if event is not None:
            raw_type = str(event["type"])
            actor_id = event.get("actor_id")
            actor = next(
                (player for player in state_view["players"] if player["id"] == actor_id),
                None,
            )
            actor_name = actor["name"] if actor else None
            amount = event.get("amount")
            if raw_type == "action" and event.get("action"):
                event_type = "action"
                action_kind = ActionKind(str(event["action"]))
                action = action_kind.value
                label = f"{actor_name or actor_id}: {ACTION_LABELS[action_kind]}"
            elif raw_type == "set_card":
                event_type = "card"
                slot = str(event.get("slot") or "")
                label = f"Carte saisie: {event.get('card')} — {slot_labels.get(slot, slot)}"
            elif raw_type == "clear_card":
                event_type = "card"
                slot = str(event.get("slot") or "")
                label = f"Carte effacée — {slot_labels.get(slot, slot)}"
            else:
                event_type = raw_type
                label = raw_type.replace("_", " ").capitalize()
        known_cards = [*state_view["hand"]["hero_cards"], *state_view["hand"]["board"]]
        is_decision_state = cursor == final_cursor
        steps.append(
            {
                "index": len(steps),
                "cursor": cursor,
                "event_type": event_type,
                "label": label,
                "actor_id": actor_id,
                "actor_name": actor_name,
                "action": action,
                "amount": amount,
                "pot": state_view["hand"]["pot"],
                "street": state_view["hand"]["street"],
                "next_actor_id": state_view["hand"]["active_player_id"],
                "known_cards": known_cards,
                "table_state": state_view,
                "estimated_ranges": {
                    player_id: ["Range probabiliste figée au moment de la décision"]
                    for player_id in opponents
                },
                "opponent_profiles": {
                    player_id: {
                        "estimated": model.estimated_profile,
                        "confidence": model.confidence,
                        "hands_observed": model.hands_observed,
                    }
                    for player_id, model in opponents.items()
                },
                "advice": (
                    {
                        "balanced": ACTION_LABELS[advice.balanced_action],
                        "exploitative": ACTION_LABELS[advice.exploit_action],
                        "final": ACTION_LABELS[advice.primary_action],
                        "recommended_amount": advice.recommended_total,
                        "confidence": advice.confidence,
                    }
                    if is_decision_state
                    else None
                ),
            }
        )
    return steps


def decision_detail_view(session: PokerSession, advice: Advice) -> dict[str, Any]:
    base = history_decision_view(session, advice)
    snapshot = session.decision_snapshots[advice.id]
    engine = HoldemEngine.restore(snapshot)
    state = engine.state
    opponents = session.opponents_from_snapshot(snapshot)
    opponent_ids = base["opponent_ids"]
    stats = {
        f"{player_id}.vpip": opponents[player_id].stats["vpip"].mean
        for player_id in opponent_ids
        if player_id in opponents
    }
    return {
        **base,
        "table_state": table_state_view(
            session,
            state=state,
            current_advice=None,
            persistence_status="saved",
            opponents=opponents,
            big_blind=engine.config.big_blind,
        ),
        "known_cards": state.hero_cards + state.board,
        "prior_actions": table_state_view(
            session,
            state=state,
            current_advice=None,
            persistence_status="saved",
            opponents=opponents,
            big_blind=engine.config.big_blind,
        )["hand"]["action_log"],
        "replay_steps": _decision_replay_steps(session, advice, snapshot, opponents),
        "estimated_ranges": {
            player_id: ["Range probabiliste pondérée; aucune main réelle supposée"]
            for player_id in opponent_ids
        },
        "statistics_used": stats,
        "pot_odds": advice.pot_odds,
        "equity": advice.equity,
        "spr": advice.spr,
        "action_evs": [
            {
                "action": item.action.value,
                "label": ACTION_LABELS[item.action],
                "amount": item.amount,
                "frequency": item.frequency,
                "ev": item.guarded_ev,
            }
            for item in advice.alternatives
        ],
        "real_result": advice.result_net or 0,
        "detailed_explanation": advice.detailed_explanation or advice.explanation,
        "limitations": advice.limitations,
    }


def opponent_view(session: PokerSession, model: OpponentModel) -> dict[str, Any]:
    sizings = [
        model.sizing_sum_by_street[street] / count
        for street, count in model.sizing_count_by_street.items()
        if count > 0
    ]
    revealed = []
    exports = [*session.archived_hands, session.engine.export()]
    for payload in exports:
        engine = HoldemEngine.restore(payload)
        cards = engine.state.revealed_hands.get(model.player_id)
        if cards:
            result = engine.state.result
            revealed.append(
                {
                    "hand_id": engine.state.id,
                    "date": next(
                        (
                            event.created_at
                            for event in reversed(engine.state.events)
                            if event.type.value == "showdown"
                        ),
                        datetime.now(UTC),
                    ),
                    "cards": cards,
                    "classification": result.hand_ranks.get(model.player_id, "inconnue")
                    if result
                    else "inconnue",
                    "bluff_observed": bool(
                        result
                        and result.hand_ranks.get(model.player_id) == "carte haute"
                        and any(
                            event.actor_id == model.player_id
                            and event.action
                            in {ActionKind.BET, ActionKind.RAISE, ActionKind.ALL_IN}
                            for event in engine.state.events
                        )
                    ),
                }
            )
    vpip = model.stats["vpip"].mean
    pfr = model.stats["pfr"].mean
    aggression = model.stats["aggression"].mean
    recommendations = []
    if vpip > 0.40:
        recommendations.append("Élargir les mises de valorisation; réduire les bluffs marginaux.")
    if model.stats["fold_to_cbet"].mean > 0.58:
        recommendations.append("Tester davantage de continuation bets à faible risque.")
    if aggression > 0.58 or pfr > 0.50:
        recommendations.append(
            "Protéger la range de check et élargir prudemment les bluff-catchers."
        )
    if not recommendations:
        recommendations.append(
            "Rester proche de la stratégie de référence tant que la confiance est limitée."
        )
    return {
        "id": model.player_id,
        "name": model.name,
        "initial_profile": _frontend_profile(model.initial_profile.value),
        "estimated_profile": model.estimated_profile,
        "confidence": model.confidence,
        "hands_observed": model.hands_observed,
        "stats": {
            "vpip": vpip,
            "pfr": pfr,
            "three_bet": model.stats["three_bet"].mean,
            "fold_to_cbet": model.stats["fold_to_cbet"].mean,
            "aggression_factor": aggression / max(0.01, 1.0 - aggression),
            "average_bet_percent": sum(sizings) / len(sizings) if sizings else 0.0,
        },
        "recent_trends": [
            f"VPIP récent estimé {model.stats['vpip'].recent_mean:.0%}",
            f"Agression récente estimée {model.stats['aggression'].recent_mean:.0%}",
        ],
        "hypotheses": [
            f"Profil statistique: {model.estimated_profile}",
            *(
                [f"A priori personnalisé déclaré: {model.custom_profile}"]
                if model.custom_profile
                else []
            ),
            "Hypothèse statistique, pas certitude psychologique.",
        ],
        "ranges_by_position": {
            position: f"VPIP estimé {stats.get('vpip', model.stats['vpip']).mean:.0%}"
            for position, stats in model.position_stats.items()
        },
        "frequent_sizings": sizings,
        "revealed_showdowns": revealed,
        "notes": model.notes,
        "recommended_adaptations": recommendations,
        "adaptation_enabled": model.exploit_enabled,
        "evolution": [
            {"hand": model.hands_observed, "vpip": vpip, "pfr": pfr, "aggression": aggression}
        ]
        if model.hands_observed
        else [],
    }


def exit_report_view(session: PokerSession) -> dict[str, Any]:
    summary = session.session_summary()
    decisions = session.advice_history
    decision_rows = [history_decision_view(session, advice) for advice in decisions]
    qualities = [row["quality"] for row in decision_rows]
    mistakes_by_street: dict[str, int] = {}
    for advice, quality in zip(decisions, qualities, strict=True):
        if quality in {"questionable", "mistake"}:
            key = _street(advice.street)
            mistakes_by_street[key] = mistakes_by_street.get(key, 0) + 1
    followed = sum(advice.actual_action == advice.primary_action for advice in decisions)
    follow_rate = followed / len(decisions) if decisions else 0.0
    quality_weights = {"excellent": 100, "acceptable": 75, "questionable": 40, "mistake": 10}
    session_score = (
        round(sum(quality_weights[quality] for quality in qualities) / len(qualities))
        if qualities
        else 0
    )
    average_confidence = (
        sum(float(row["confidence"]) for row in decision_rows) / len(decision_rows)
        if decision_rows
        else 0.0
    )
    total_ev_loss_bb = sum(
        max(0.0, float(row["ev_difference"])) / max(1, int(row["big_blind"]))
        for row in decision_rows
    )
    costly_decisions = sorted(
        (
            {
                "id": str(row["id"]),
                "hand_number": int(row["hand_number"]),
                "street": str(row["street"]),
                "chosen_action": str(row["chosen_action"]),
                "recommended_action": str(row["final_advice"]),
                "ev_loss_bb": round(
                    max(0.0, float(row["ev_difference"])) / max(1, int(row["big_blind"])),
                    2,
                ),
                "confidence": round(float(row["confidence"]), 4),
                "explanation": str(row["short_explanation"]),
            }
            for row in decision_rows
            if row["quality"] in {"questionable", "mistake"}
        ),
        key=lambda item: cast(float, item["ev_loss_bb"]),
        reverse=True,
    )[:3]

    street_labels = {
        "preflop": "préflop",
        "flop": "flop",
        "turn": "turn",
        "river": "river",
        "showdown": "showdown",
        "terminee": "fin de main",
    }
    learning_plan: list[dict[str, str]] = []
    if mistakes_by_street:
        weakest_street, weakest_count = max(
            mistakes_by_street.items(), key=lambda item: (item[1], item[0])
        )
        weakest_label = street_labels.get(weakest_street, weakest_street)
        learning_plan.append(
            {
                "title": f"Rejouer les décisions au {weakest_label}",
                "reason": (
                    f"{weakest_count} décision(s) à revoir sur cette rue, "
                    "évaluées indépendamment du résultat final."
                ),
                "drill": (
                    "Ouvrir les mains concernées, masquer le conseil final, puis justifier "
                    "une action avec l'équité, les pot odds et la profondeur effective."
                ),
            }
        )
    if total_ev_loss_bb >= 0.25:
        learning_plan.append(
            {
                "title": "Réduire les décisions les plus coûteuses",
                "reason": f"La session cumule {total_ev_loss_bb:.2f} BB d'écart d'EV estimé.",
                "drill": (
                    "Rejouer les trois plus gros écarts et comparer l'action choisie à "
                    "l'action recommandée sans regarder le gain ou la perte de la main."
                ),
            }
        )
    if decisions and follow_rate < 0.70:
        learning_plan.append(
            {
                "title": "Clarifier le raisonnement avant d'agir",
                "reason": f"Le conseil principal a été suivi dans {follow_rate:.0%} des décisions.",
                "drill": (
                    "Avant chaque action, annoncer mentalement range, pot odds et objectif "
                    "du sizing, "
                    "puis comparer cette hypothèse au conseil affiché."
                ),
            }
        )
    if decisions and average_confidence < 0.60:
        learning_plan.append(
            {
                "title": "Améliorer la qualité des observations",
                "reason": f"La confiance moyenne des estimations est de {average_confidence:.0%}.",
                "drill": (
                    "Collecter davantage de showdowns et vérifier les profils adverses avant "
                    "d'appliquer une adaptation exploitante forte."
                ),
            }
        )
    if not learning_plan:
        learning_plan.append(
            {
                "title": "Consolider les bonnes décisions",
                "reason": "Aucun axe prioritaire ne ressort encore de cette session.",
                "drill": (
                    "Rejouer deux décisions représentatives et expliquer pourquoi l'action "
                    "retenue reste robuste face à plusieurs profils adverses."
                ),
            }
        )
    learning_plan = learning_plan[:3]

    strengths: list[str] = []
    if session_score >= 75:
        strengths.append("Décisions globalement solides selon l'EV estimée")
    if decisions and follow_rate >= 0.75:
        strengths.append("Bonne discipline par rapport au plan recommandé")
    if decisions and average_confidence >= 0.70:
        strengths.append("Décisions prises avec un contexte statistique suffisamment étayé")
    if not costly_decisions and decisions:
        strengths.append("Aucune décision fortement coûteuse détectée")
    if not strengths:
        strengths.append("Historique exploitable pour construire un plan de progression mesurable")

    coach_summary = (
        "Session maîtrisée : conserver le processus et approfondir les décisions marginales."
        if session_score >= 85
        else "Base solide : quelques décisions ciblées peuvent encore améliorer la régularité."
        if session_score >= 65
        else (
            "Priorité à la méthode : revoir les décisions coûteuses avant d'augmenter "
            "la complexité."
        )
        if decisions
        else "Jouez quelques mains avec le conseil actif pour obtenir un diagnostic personnalisé."
    )
    return {
        "session_id": session.id,
        "unit": session.config.unit.value,
        "big_blind": session.config.big_blind,
        "started_at": session.created_at,
        "ended_at": datetime.now(UTC),
        "hands_played": summary["hands_played"],
        "initial_stack": summary["initial_hero_stack"],
        "final_stack": summary["final_hero_stack"],
        "net_result": summary["net_result"],
        "net_result_bb": summary["net_result_big_blinds"],
        "hands_won": summary["hands_won"],
        "hands_lost": summary["hands_lost"],
        "split_pots": summary["split_pots"],
        "wins_without_showdown": summary["wins_without_showdown"],
        "showdown_wins": summary["showdown_wins"],
        "biggest_pot_won": summary["biggest_pot_won"],
        "biggest_pot_lost": summary["biggest_pot_lost"],
        "decisions": len(decisions),
        "excellent": qualities.count("excellent"),
        "acceptable": qualities.count("acceptable"),
        "mistakes": qualities.count("questionable") + qualities.count("mistake"),
        "advice_follow_rate": follow_rate,
        "street_mistakes": mistakes_by_street,
        "insights": [
            "La qualité des décisions est évaluée par l'EV estimée, "
            "indépendamment du résultat de la main.",
            "Les adaptations adverses restent régularisées vers le profil neutre "
            "avec peu d'observations.",
        ],
        "coach": {
            "session_score": session_score,
            "summary": coach_summary,
            "decisions_reviewed": len(decision_rows),
            "total_ev_loss_bb": round(total_ev_loss_bb, 2),
            "average_confidence": round(average_confidence, 4),
            "strengths": strengths,
            "top_decisions": costly_decisions,
            "learning_plan": learning_plan,
            "methodology": (
                "Le coach agrège les écarts d'EV, la confiance et la régularité des décisions. "
                "Le résultat financier d'une main n'améliore ni ne dégrade sa note."
            ),
        },
    }
