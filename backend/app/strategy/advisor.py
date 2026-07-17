from __future__ import annotations

import json
from collections import OrderedDict
from datetime import UTC, datetime
from hashlib import sha256
from math import exp
from random import Random
from uuid import uuid4

import numpy as np

from app.models import (
    ActionEvaluation,
    ActionKind,
    Advice,
    AnalysisLevel,
    HandState,
    PlayerState,
    PlayerStatus,
    SessionCreate,
    Street,
)
from app.opponents.model import OpponentModel
from app.strategy.equity import RangeParameters, estimate_equity
from app.strategy.local_solver import solve_zero_sum
from app.strategy.preflop import PREFLOP_TABLE_VERSION, chart_decision

ACTION_NAME = {
    ActionKind.FOLD: "Fold",
    ActionKind.CHECK: "Check",
    ActionKind.CALL: "Call",
    ActionKind.BET: "Raise",
    ActionKind.RAISE: "Raise",
    ActionKind.ALL_IN: "All-in",
}


def _action_label(item: ActionEvaluation) -> str:
    """Libellé d'une alternative, avec le montant quand il existe.

    Deux tailles de relance différentes portent sinon le même nom générique
    ("Raise"), ce qui rend les textes de comparaison ambigus; le montant
    lève cette ambiguïté.
    """
    base = ACTION_NAME[item.action]
    if item.amount is None:
        return base
    return f"{base} à {item.amount}"


def pot_odds(pot: int, to_call: int) -> float:
    return 0.0 if to_call <= 0 else to_call / (pot + to_call)


def stack_to_pot_ratio(effective_stack: int, pot: int) -> float:
    return float("inf") if pot <= 0 else effective_stack / pot


class StrategyAdvisor:
    """Conseil calculé sans LLM; toute sortie avancée est explicitement estimative."""

    def __init__(self, *, cache_size: int = 256) -> None:
        self._cache_size = max(1, cache_size)
        self._cache: OrderedDict[str, Advice] = OrderedDict()
        self.cache_hits = 0
        self.cache_misses = 0

    def advise(
        self,
        *,
        session_id: str,
        config: SessionCreate,
        state: HandState,
        opponents: dict[str, OpponentModel],
        level: AnalysisLevel = AnalysisLevel.FAST,
        trials: int | None = None,
        seed: int | None = None,
    ) -> Advice:
        if state.actor_id != "hero":
            raise ValueError("Le conseil est disponible uniquement lorsque Ryanchl doit agir")
        if len(state.hero_cards) != 2:
            raise ValueError("Sélectionnez les deux cartes de Ryanchl avant de demander un conseil")
        seed_value = seed if seed is not None else self._stable_seed(session_id, state)
        trial_count = (
            trials
            or {
                AnalysisLevel.FAST: 700,
                AnalysisLevel.DEEP: 4_000,
                AnalysisLevel.EXPERT: 15_000,
            }[level]
        )
        cache_key = self._cache_key(
            config=config,
            state=state,
            opponents=opponents,
            level=level,
            trials=trial_count,
            seed=seed_value,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            self.cache_hits += 1
            self._cache.move_to_end(cache_key)
            return cached.model_copy(
                deep=True,
                update={
                    "id": str(uuid4()),
                    "session_id": session_id,
                    "hand_id": state.id,
                    "street": state.street,
                    "created_at": datetime.now(UTC),
                    "detailed_explanation": None,
                    "explanation_pending": True,
                    "actual_action": None,
                    "actual_amount": None,
                    "ev_difference": None,
                    "result_net": None,
                },
            )
        self.cache_misses += 1
        hero = next(player for player in state.players if player.id == "hero")
        active_opponents = [
            player
            for player in state.players
            if player.id != "hero"
            and player.status
            not in {PlayerStatus.FOLDED, PlayerStatus.ABSENT, PlayerStatus.ELIMINATED}
        ]
        ranges = [self._range_for(opponents.get(player.id), state) for player in active_opponents]
        equity = estimate_equity(
            state.hero_cards,
            state.board,
            ranges,
            trials=trial_count,
            seed=seed_value,
        )
        call_descriptor = next(
            (
                item
                for item in state.legal_actions
                if item.action == ActionKind.CALL and item.enabled
            ),
            None,
        )
        to_call = call_descriptor.to_call if call_descriptor else 0
        pot = sum(player.total_contribution for player in state.players)
        opponent_stack = max((player.stack for player in active_opponents), default=0)
        effective = min(hero.stack, opponent_stack) if active_opponents else hero.stack
        odds = pot_odds(pot, min(to_call, hero.stack))
        spr = stack_to_pot_ratio(effective, pot)
        model_confidence = self._model_confidence(opponents, active_opponents)
        balanced_fold_equity = max(0.08, min(0.65, 0.32 + 0.05 * (len(state.board) - 3)))
        exploit_fold_equity = self._exploit_fold_equity(
            opponents, active_opponents, balanced_fold_equity, state.street
        )
        candidates = self._candidates(state, config.big_blind)
        evaluations = self._evaluate_candidates(
            candidates,
            equity=equity.equity,
            pot=pot,
            to_call=to_call,
            street_contribution=hero.street_contribution,
            current_bet=state.current_bet,
            balanced_fold_equity=balanced_fold_equity,
            exploit_fold_equity=exploit_fold_equity,
            model_confidence=model_confidence,
        )
        source = "monte_carlo_ranges_ponderees"
        precision = "monte_carlo_estimate"
        if state.street == Street.PREFLOP:
            facing_raise = any(
                event.payload.get("resolved_action", event.action.value if event.action else "")
                in {ActionKind.RAISE.value, ActionKind.BET.value}
                for event in state.events
                if event.type.value == "action"
            )
            raise_count = sum(
                event.payload.get("resolved_action", event.action.value if event.action else "")
                in {ActionKind.RAISE.value, ActionKind.BET.value}
                for event in state.events
                if event.type.value == "action"
            )
            chart = chart_decision(
                state.hero_cards,
                position=hero.position,
                stack_bb=(hero.stack + hero.total_contribution) / config.big_blind,
                facing_raise=facing_raise,
                raise_count=raise_count,
            )
            evaluations = self._apply_chart(evaluations, chart.action, pot, config.big_blind)
            source = f"{PREFLOP_TABLE_VERSION}+monte_carlo_ranges"
            precision = "monte_carlo_estimate"
        evaluations = self._frequencies(evaluations, pot)
        if level in {AnalysisLevel.DEEP, AnalysisLevel.EXPERT}:
            evaluations = self._apply_local_solver(
                evaluations,
                iterations=1_000 if level == AnalysisLevel.DEEP else 3_000,
            )
            source += "+regret_matching_local"
        balanced_best = max(evaluations, key=lambda item: item.balanced_ev)
        exploit_best = max(evaluations, key=lambda item: item.exploit_ev)
        final_best = max(evaluations, key=lambda item: item.guarded_ev)
        sampled = self._sample_action(evaluations, seed_value)
        confidence = min(
            0.92,
            0.45 + min(0.30, trial_count / 20_000) + model_confidence * 0.20,
        )
        explanation = self._explain(
            final_best,
            equity.equity,
            odds,
            spr,
            model_confidence,
            exploit_best.action != balanced_best.action,
        )
        sorted_evaluations = sorted(evaluations, key=lambda item: item.guarded_ev, reverse=True)
        advice = Advice(
            id=str(uuid4()),
            session_id=session_id,
            hand_id=state.id,
            street=state.street,
            primary_action=final_best.action,
            recommended_total=final_best.amount,
            frequency=final_best.frequency,
            balanced_action=balanced_best.action,
            exploit_action=exploit_best.action,
            sampled_action=sampled.action,
            alternatives=sorted_evaluations,
            equity=equity.equity,
            equity_required=odds,
            pot_odds=odds,
            spr=spr,
            effective_stack=effective,
            fold_equity=exploit_fold_equity,
            confidence=confidence,
            analysis_level=level,
            source=source,
            precision=precision,
            seed=seed_value,
            trials=trial_count,
            explanation=explanation,
            limitations=[
                "Les cartes adverses sont échantillonnées temporairement "
                "depuis des ranges et ne sont jamais conservées.",
                "Les EV futures utilisent une abstraction de réponses et de sizings, "
                "pas un équilibre complet du jeu.",
                "L'adaptation exploitante est plafonnée par la confiance bayésienne du profil.",
            ],
        )
        self._cache[cache_key] = advice.model_copy(deep=True)
        self._cache.move_to_end(cache_key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return advice

    @property
    def cache_entries(self) -> int:
        return len(self._cache)

    @staticmethod
    def _cache_key(
        *,
        config: SessionCreate,
        state: HandState,
        opponents: dict[str, OpponentModel],
        level: AnalysisLevel,
        trials: int,
        seed: int,
    ) -> str:
        semantic_state = {
            "street": state.street.value,
            "hero_cards": state.hero_cards,
            "board": state.board,
            "actor_id": state.actor_id,
            "current_bet": state.current_bet,
            "last_full_raise": state.last_full_raise,
            "players": [
                {
                    "id": player.id,
                    "position": player.position,
                    "stack": player.stack,
                    "street_contribution": player.street_contribution,
                    "total_contribution": player.total_contribution,
                    "status": player.status.value,
                }
                for player in state.players
            ],
            "events": [
                {
                    "type": event.type.value,
                    "actor_id": event.actor_id,
                    "action": event.action.value if event.action else None,
                    "amount": event.amount,
                    "total": event.total,
                    "slot": event.slot,
                    "card": event.card,
                    "street": event.payload.get("street"),
                    "resolved_action": event.payload.get("resolved_action"),
                    "raise_count": event.payload.get("raise_count"),
                }
                for event in state.events
            ],
            "legal_actions": [item.model_dump(mode="json") for item in state.legal_actions],
        }
        semantic_opponents = {
            player_id: {
                "initial_profile": model.initial_profile.value,
                "exploit_enabled": model.exploit_enabled,
                "confidence": model.confidence,
                "stats": {
                    name: {
                        "mean": stat.mean,
                        "recent_mean": stat.recent_mean,
                        "opportunities": stat.raw_opportunities,
                    }
                    for name, stat in sorted(model.stats.items())
                },
            }
            for player_id, model in sorted(opponents.items())
        }
        payload = {
            "strategy_version": f"{PREFLOP_TABLE_VERSION}:local-solver-1",
            "big_blind": config.big_blind,
            "level": level.value,
            "trials": trials,
            "seed": seed,
            "state": semantic_state,
            "opponents": semantic_opponents,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def detailed_explanation(advice: Advice) -> str:
        best = max(advice.alternatives, key=lambda item: item.guarded_ev)
        best_label = _action_label(best)
        ordered = sorted(advice.alternatives, key=lambda item: item.guarded_ev, reverse=True)
        runner_up = next((item for item in ordered if _action_label(item) != best_label), best)
        return (
            f"Analyse structurée: {best_label} obtient une EV gardée estimée de "
            f"{best.guarded_ev:.2f}, contre {runner_up.guarded_ev:.2f} pour "
            f"{_action_label(runner_up)}. L'équité Monte-Carlo est {advice.equity:.1%} "
            f"pour un seuil de {advice.equity_required:.1%}, avec un SPR de {advice.spr:.2f} "
            f"et une fold equity estimée à {advice.fold_equity:.1%}. La pondération exploitante "
            f"reste bornée par une confiance de {advice.confidence:.1%}. Aucun nouveau calcul du "
            "solveur n'a été lancé pour produire ce texte; il dérive exclusivement des métriques "
            "déjà enregistrées."
        )

    @staticmethod
    def _stable_seed(session_id: str, state: HandState) -> int:
        material = (
            f"{session_id}:{state.id}:{len(state.events)}:"
            f"{','.join(state.hero_cards)}:{','.join(state.board)}"
        )
        return sum((index + 1) * ord(character) for index, character in enumerate(material)) % (
            2**31
        )

    @staticmethod
    def _range_for(model: OpponentModel | None, state: HandState) -> RangeParameters:
        if model is None:
            return RangeParameters()
        vpip = model.stats["vpip"].mean
        aggression = model.stats["aggression"].mean
        raised = any(
            event.actor_id == model.player_id
            and event.payload.get("street") == Street.PREFLOP.value
            and event.payload.get("resolved_action", event.action.value if event.action else "")
            in {ActionKind.RAISE.value, ActionKind.BET.value}
            for event in state.events
        )
        return RangeParameters(vpip=vpip, aggression=aggression, preflop_raise=raised)

    @staticmethod
    def _model_confidence(
        opponents: dict[str, OpponentModel], active_players: list[PlayerState]
    ) -> float:
        ids = [player.id for player in active_players]
        confidences = [
            opponents[player_id].confidence
            for player_id in ids
            if player_id in opponents and opponents[player_id].exploit_enabled
        ]
        return sum(confidences) / len(confidences) if confidences else 0.0

    @staticmethod
    def _exploit_fold_equity(
        opponents: dict[str, OpponentModel],
        active_players: list[PlayerState],
        baseline: float,
        street: Street,
    ) -> float:
        estimates: list[tuple[float, float]] = []
        for player in active_players:
            player_id = player.id
            model = opponents.get(player_id)
            if model is not None and model.exploit_enabled:
                stat_name = "fold_to_open" if street == Street.PREFLOP else "fold_to_cbet"
                fold = model.stats[stat_name].mean
                estimates.append((fold, model.confidence))
        if not estimates:
            return baseline
        weighted = sum(value * confidence for value, confidence in estimates)
        total_confidence = sum(confidence for _, confidence in estimates)
        observed = weighted / total_confidence if total_confidence else baseline
        guard = min(0.55, total_confidence / max(1, len(estimates)))
        return max(0.05, min(0.80, baseline * (1 - guard) + observed * guard))

    @staticmethod
    def _candidates(state: HandState, big_blind: int) -> list[tuple[ActionKind, int | None]]:
        legal = {item.action: item for item in state.legal_actions if item.enabled}
        candidates: list[tuple[ActionKind, int | None]] = []
        for action in (ActionKind.FOLD, ActionKind.CHECK, ActionKind.CALL):
            if action in legal:
                candidates.append((action, legal[action].max_total))
        for action in (ActionKind.BET, ActionKind.RAISE):
            if action not in legal:
                continue
            descriptor = legal[action]
            minimum = descriptor.min_total or big_blind
            maximum = descriptor.max_total or minimum
            pot = max(big_blind, state.pot)
            to_call = 0
            if state.actor_id:
                actor = next(player for player in state.players if player.id == state.actor_id)
                to_call = max(0, state.current_bet - actor.street_contribution)
            pot_after_call = pot + to_call
            totals = {minimum, maximum}
            for fraction in (0.25, 0.33, 0.5, 0.66, 0.75, 1.0, 1.25, 1.5, 2.0):
                if action == ActionKind.BET:
                    target = round(pot * fraction)
                else:
                    target = state.current_bet + round(pot_after_call * fraction)
                totals.add(max(minimum, min(maximum, target)))
            candidates.extend((action, total) for total in sorted(totals))
        if ActionKind.ALL_IN in legal:
            all_in_total = legal[ActionKind.ALL_IN].max_total
            if not any(amount == all_in_total for _, amount in candidates):
                candidates.append((ActionKind.ALL_IN, all_in_total))
        return candidates

    @staticmethod
    def _evaluate_candidates(
        candidates: list[tuple[ActionKind, int | None]],
        *,
        equity: float,
        pot: int,
        to_call: int,
        street_contribution: int,
        current_bet: int,
        balanced_fold_equity: float,
        exploit_fold_equity: float,
        model_confidence: float,
    ) -> list[ActionEvaluation]:
        evaluations: list[ActionEvaluation] = []
        for action, amount in candidates:
            if action == ActionKind.FOLD:
                balanced_ev = exploit_ev = 0.0
            elif action == ActionKind.CHECK:
                balanced_ev = exploit_ev = equity * pot
            elif action == ActionKind.CALL or (
                action == ActionKind.ALL_IN and (amount or 0) <= current_bet
            ):
                cost = min(to_call, max(0, (amount or street_contribution) - street_contribution))
                balanced_ev = exploit_ev = equity * (pot + cost) - cost
            else:
                target = amount or current_bet
                cost = max(0, target - street_contribution)
                opponent_call = max(0, target - current_bet)
                called_pot = pot + cost + opponent_call
                balanced_ev = balanced_fold_equity * pot + (1 - balanced_fold_equity) * (
                    equity * called_pot - cost
                )
                exploit_ev = exploit_fold_equity * pot + (1 - exploit_fold_equity) * (
                    equity * called_pot - cost
                )
            guarded = balanced_ev + min(0.55, model_confidence) * (exploit_ev - balanced_ev)
            evaluations.append(
                ActionEvaluation(
                    action=action,
                    amount=amount,
                    balanced_ev=balanced_ev,
                    exploit_ev=exploit_ev,
                    guarded_ev=guarded,
                    frequency=0.0,
                    acceptable=False,
                )
            )
        return evaluations

    @staticmethod
    def _apply_chart(
        evaluations: list[ActionEvaluation], preferred: ActionKind, pot: int, big_blind: int
    ) -> list[ActionEvaluation]:
        available_actions = {evaluation.action for evaluation in evaluations}
        if preferred not in available_actions:
            preferred = (
                ActionKind.CHECK
                if ActionKind.CHECK in available_actions
                else (
                    ActionKind.CALL
                    if ActionKind.CALL in available_actions
                    else max(evaluations, key=lambda item: item.guarded_ev).action
                )
            )
        bonus = max(big_blind, pot * 0.35)
        return [
            evaluation.model_copy(
                update={
                    "balanced_ev": evaluation.balanced_ev
                    + (bonus if evaluation.action == preferred else 0.0),
                    "guarded_ev": evaluation.guarded_ev
                    + (bonus if evaluation.action == preferred else 0.0),
                }
            )
            for evaluation in evaluations
        ]

    @staticmethod
    def _frequencies(evaluations: list[ActionEvaluation], pot: int) -> list[ActionEvaluation]:
        best = max(item.guarded_ev for item in evaluations)
        temperature = max(1.0, pot * 0.10)
        weights = [exp(max(-40.0, (item.guarded_ev - best) / temperature)) for item in evaluations]
        total = sum(weights)
        best_ev = best
        tolerance = max(1.0, pot * 0.03)
        return [
            item.model_copy(
                update={
                    "frequency": weight / total,
                    "acceptable": best_ev - item.guarded_ev <= tolerance,
                }
            )
            for item, weight in zip(evaluations, weights, strict=True)
        ]

    @staticmethod
    def _sample_action(evaluations: list[ActionEvaluation], seed: int) -> ActionEvaluation:
        return Random(seed).choices(
            evaluations, weights=[item.frequency for item in evaluations], k=1
        )[0]

    @staticmethod
    def _apply_local_solver(
        evaluations: list[ActionEvaluation], *, iterations: int
    ) -> list[ActionEvaluation]:
        matrix = np.asarray(
            [
                [
                    item.guarded_ev,
                    item.balanced_ev
                    - (
                        0.08 * abs(item.amount or 0)
                        if item.action in {ActionKind.BET, ActionKind.RAISE, ActionKind.ALL_IN}
                        else 0.0
                    ),
                ]
                for item in evaluations
            ],
            dtype=np.float64,
        )
        solution = solve_zero_sum(matrix, iterations=iterations)
        blended = [
            item.model_copy(update={"frequency": 0.65 * item.frequency + 0.35 * solved_frequency})
            for item, solved_frequency in zip(evaluations, solution.row_strategy, strict=True)
        ]
        total = sum(item.frequency for item in blended)
        return [item.model_copy(update={"frequency": item.frequency / total}) for item in blended]

    @staticmethod
    def _explain(
        best: ActionEvaluation,
        equity: float,
        odds: float,
        spr: float,
        model_confidence: float,
        exploit_differs: bool,
    ) -> str:
        action_label = ACTION_NAME[best.action]
        comparison = "supérieure" if equity >= odds else "inférieure"
        adaptation = (
            "L'adaptation exploitante modifie le classement, mais reste plafonnée par la confiance."
            if exploit_differs
            else "La référence équilibrée et l'adaptation exploitante convergent."
        )
        confidence_text = (
            "L'échantillon adverse est encore faible; l'adaptation reste minime."
            if model_confidence < 0.25
            else "Le profil adverse possède assez d'observations pour une adaptation modérée."
        )
        return (
            f"{action_label} présente la meilleure EV estimée. "
            f"L'équité échantillonnée ({equity:.1%}) "
            f"est {comparison} au seuil des pot odds ({odds:.1%}); le SPR est {spr:.2f}. "
            f"{adaptation} {confidence_text} Cette recommandation décrit une estimation, "
            "pas une certitude."
        )
