from __future__ import annotations

import asyncio
import csv
import io
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app import __version__
from app.engine.holdem import HoldemEngine, PokerRuleError
from app.engine.session import PokerSession
from app.models import (
    ActionRequest,
    Advice,
    AnalysisRequest,
    CardRequest,
    ExitRequest,
    OpponentMerge,
    OpponentPatch,
    PlayerPatch,
    PlayerReplace,
    SessionCreate,
    ShowdownRequest,
)
from app.opponents.model import OpponentModel
from app.persistence import Database, PersistenceQueue
from app.presentation import (
    advice_view,
    decision_detail_view,
    exit_report_view,
    history_decision_view,
    opponent_view,
    table_state_view,
)
from app.strategy.advisor import StrategyAdvisor


class AppServices:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or Database()
        self.persistence = PersistenceQueue(self.database)
        self.sessions: dict[str, PokerSession] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.background_tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        await self.persistence.start()
        for payload in await self.database.load_sessions():
            try:
                session = PokerSession.restore(payload)
            except (ValueError, KeyError, TypeError):
                continue
            self.sessions[session.id] = session
            self.locks[session.id] = asyncio.Lock()

    async def stop(self) -> None:
        if self.background_tasks:
            _done, pending = await asyncio.wait(self.background_tasks, timeout=2.0)
            for task in pending:
                task.cancel()
        for session in self.sessions.values():
            self.persistence.enqueue_session(session.export())
        await self.persistence.stop()

    def get(self, session_id: str) -> PokerSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session introuvable")
        return session

    def lock(self, session_id: str) -> asyncio.Lock:
        return self.locks.setdefault(session_id, asyncio.Lock())

    def save(self, session: PokerSession) -> None:
        self.persistence.enqueue_session(session.export())

    def spawn(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)


def services(request: Request) -> AppServices:
    return request.app.state.services  # type: ignore[no-any-return]


router = APIRouter(prefix="/api")


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    service = services(request)
    return {
        "status": "ok",
        "version": __version__,
        "database": str(service.database.path),
        "persistence": service.persistence.status,
        "pending_writes": service.persistence.queue.qsize(),
        "sessions_loaded": len(service.sessions),
        "fictional_chips_only": True,
    }


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate, request: Request) -> dict[str, Any]:
    service = services(request)
    session = PokerSession(payload)
    service.sessions[session.id] = session
    service.locks[session.id] = asyncio.Lock()
    service.save(session)
    return table_state_view(session, persistence_status=service.persistence.status)


@router.get("/sessions")
async def list_sessions(request: Request) -> list[dict[str, Any]]:
    service = services(request)
    items = [
        {
            "id": session.id,
            "status": session.engine.state.status.value,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "hand_in_progress": session.engine.state.status.value != "complete",
        }
        for session in sorted(
            service.sessions.values(), key=lambda item: item.updated_at, reverse=True
        )
    ]
    return items


@router.get("/sessions/{session_id}/state")
@router.get("/sessions/{session_id}")
async def get_state(session_id: str, request: Request) -> dict[str, Any]:
    service = services(request)
    return table_state_view(service.get(session_id), persistence_status=service.persistence.status)


@router.post("/sessions/{session_id}/actions")
async def take_action(session_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
    service = services(request)
    async with service.lock(session_id):
        session = service.get(session_id)
        was_hero = session.engine.state.actor_id == "hero"
        session.take_action(payload)
        service.save(session)
        actor_id = session.engine.state.actor_id
        if actor_id != "hero":
            for player_id, model in session.opponents.items():
                service.persistence.enqueue_opponent(
                    session.id, player_id, model.model_dump(mode="json")
                )
        if was_hero:
            recorded = next(
                (item for item in reversed(session.advice_history) if item.actual_action), None
            )
            if recorded:
                service.persistence.enqueue_advice(session.id, recorded.model_dump(mode="json"))
        return table_state_view(session, persistence_status=service.persistence.status)


@router.post("/sessions/{session_id}/cards")
async def set_card(session_id: str, payload: CardRequest, request: Request) -> dict[str, Any]:
    service = services(request)
    async with service.lock(session_id):
        session = service.get(session_id)
        session.set_card(payload)
        service.save(session)
        return table_state_view(session, persistence_status=service.persistence.status)


@router.delete("/sessions/{session_id}/cards/{slot}")
async def clear_card(session_id: str, slot: str, request: Request) -> dict[str, Any]:
    service = services(request)
    async with service.lock(session_id):
        session = service.get(session_id)
        session.clear_card(slot)
        service.save(session)
        return table_state_view(session, persistence_status=service.persistence.status)


@router.post("/sessions/{session_id}/showdown")
async def showdown(session_id: str, payload: ShowdownRequest, request: Request) -> dict[str, Any]:
    service = services(request)
    async with service.lock(session_id):
        session = service.get(session_id)
        session.settle_showdown(payload)
        service.save(session)
        for player_id, model in session.opponents.items():
            service.persistence.enqueue_opponent(
                session.id, player_id, model.model_dump(mode="json")
            )
        return table_state_view(session, persistence_status=service.persistence.status)


@router.post("/sessions/{session_id}/undo")
async def undo(session_id: str, request: Request) -> dict[str, Any]:
    service = services(request)
    async with service.lock(session_id):
        session = service.get(session_id)
        session.undo()
        service.save(session)
        return table_state_view(session, persistence_status=service.persistence.status)


@router.post("/sessions/{session_id}/redo")
async def redo(session_id: str, request: Request) -> dict[str, Any]:
    service = services(request)
    async with service.lock(session_id):
        session = service.get(session_id)
        session.redo()
        service.save(session)
        return table_state_view(session, persistence_status=service.persistence.status)


@router.post("/sessions/{session_id}/restart-hand")
async def restart_hand(session_id: str, request: Request) -> dict[str, Any]:
    service = services(request)
    async with service.lock(session_id):
        session = service.get(session_id)
        session.restart_hand()
        service.save(session)
        return table_state_view(session, persistence_status=service.persistence.status)


@router.post("/sessions/{session_id}/next-hand")
async def next_hand(session_id: str, request: Request) -> dict[str, Any]:
    service = services(request)
    async with service.lock(session_id):
        session = service.get(session_id)
        session.next_hand()
        service.save(session)
        return table_state_view(session, persistence_status=service.persistence.status)


@router.patch("/sessions/{session_id}/players/{player_id}")
async def patch_player(
    session_id: str, player_id: str, payload: PlayerPatch, request: Request
) -> dict[str, Any]:
    service = services(request)
    async with service.lock(session_id):
        session = service.get(session_id)
        session.patch_player(player_id, payload)
        service.save(session)
        return table_state_view(session, persistence_status=service.persistence.status)


@router.post("/sessions/{session_id}/players/{player_id}/replace")
async def replace_player(
    session_id: str, player_id: str, payload: PlayerReplace, request: Request
) -> dict[str, Any]:
    service = services(request)
    if player_id == "hero":
        raise HTTPException(status_code=422, detail="Le joueur principal ne peut pas être remplacé")
    async with service.lock(session_id):
        session = service.get(session_id)
        session.replace_player(player_id, payload)
        service.save(session)
        model = session.opponents.get(player_id)
        if model is not None:
            service.persistence.enqueue_opponent(
                session.id, player_id, model.model_dump(mode="json")
            )
        return table_state_view(session, persistence_status=service.persistence.status)


@router.delete("/sessions/{session_id}/players/{player_id}/seat")
async def remove_player_from_seat(
    session_id: str, player_id: str, request: Request
) -> dict[str, Any]:
    service = services(request)
    async with service.lock(session_id):
        session = service.get(session_id)
        session.remove_player(player_id)
        service.save(session)
        return table_state_view(session, persistence_status=service.persistence.status)


@router.post("/sessions/{session_id}/players/{player_id}/seat")
async def seat_player(
    session_id: str, player_id: str, payload: PlayerReplace, request: Request
) -> dict[str, Any]:
    service = services(request)
    async with service.lock(session_id):
        session = service.get(session_id)
        session.seat_player(player_id, payload)
        service.save(session)
        model = session.opponents.get(player_id)
        if model is not None:
            service.persistence.enqueue_opponent(
                session.id, player_id, model.model_dump(mode="json")
            )
        return table_state_view(session, persistence_status=service.persistence.status)


async def _calculate_advice(
    session: PokerSession, payload: AnalysisRequest
) -> tuple[Advice, dict[str, Any], datetime]:
    engine_payload = session.engine.export()
    marker = session.updated_at
    engine = HoldemEngine.restore(engine_payload)
    opponent_copies = {
        player_id: OpponentModel.model_validate(model.model_dump())
        for player_id, model in session.opponents.items()
    }
    advisor = StrategyAdvisor()
    advice = await asyncio.to_thread(
        advisor.advise,
        session_id=session.id,
        config=session.config,
        state=engine.state,
        opponents=opponent_copies,
        level=payload.level,
        trials=payload.trials,
        seed=payload.seed,
    )
    snapshot = {
        **engine_payload,
        "history_context": PokerSession.history_context(engine),
        "opponents_at_decision": {
            player_id: model.model_dump(mode="json") for player_id, model in opponent_copies.items()
        },
    }
    return advice, snapshot, marker


async def _complete_advice_explanation(
    service: AppServices,
    session_id: str,
    advice_id: str,
    delay_ms: int,
) -> None:
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1_000)
    session = service.sessions.get(session_id)
    if session is None:
        return
    async with service.lock(session_id):
        advice = next((item for item in session.advice_history if item.id == advice_id), None)
        if advice is None:
            return
        advice.detailed_explanation = StrategyAdvisor.detailed_explanation(advice)
        advice.explanation_pending = False
        service.persistence.enqueue_advice(session.id, advice.model_dump(mode="json"))
        service.save(session)


@router.post("/sessions/{session_id}/advice")
async def post_advice(
    session_id: str, payload: AnalysisRequest, request: Request
) -> dict[str, Any]:
    service = services(request)
    session = service.get(session_id)
    advice, snapshot, marker = await _calculate_advice(session, payload)
    async with service.lock(session_id):
        session = service.get(session_id)
        if session.updated_at != marker or session.engine.hand_id != advice.hand_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "L'état de la table a changé pendant l'analyse; "
                    "le conseil obsolète a été ignoré"
                ),
            )
        session.advice_history.append(advice)
        session.decision_snapshots[advice.id] = snapshot
        session.current_advice = advice
        session.updated_at = advice.created_at
        service.persistence.enqueue_advice(session.id, advice.model_dump(mode="json"))
        service.save(session)
        try:
            delay_ms = max(0, int(os.environ.get("POKER_IA_EXPLANATION_DELAY_MS", "0")))
        except ValueError:
            delay_ms = 0
        service.spawn(_complete_advice_explanation(service, session.id, advice.id, delay_ms))
        return advice_view(advice)


@router.get("/sessions/{session_id}/advice")
async def get_advice(session_id: str, request: Request) -> dict[str, Any]:
    service = services(request)
    session = service.get(session_id)
    if (
        session.current_advice is not None
        and session.current_advice.hand_id == session.engine.hand_id
    ):
        return advice_view(session.current_advice)
    return await post_advice(session_id, AnalysisRequest(), request)


@router.get("/history")
async def history(
    request: Request,
    session_id: str | None = None,
    street: str | None = None,
    position: str | None = None,
    sort_by: str = Query(default="date", pattern="^(date|ev_difference|result|confidence)$"),
    descending: bool = True,
) -> list[dict[str, Any]]:
    service = services(request)
    sessions = [service.get(session_id)] if session_id else list(service.sessions.values())
    items = [
        history_decision_view(session, advice)
        for session in sessions
        for advice in session.advice_history
    ]
    if street:
        items = [item for item in items if item["street"] == street]
    if position:
        items = [item for item in items if item["position"] == position]
    key_functions = {
        "date": lambda item: item["date"].timestamp(),
        "ev_difference": lambda item: item["ev_difference"],
        "result": lambda item: float(item["hand_result"]),
        "confidence": lambda item: item["confidence"],
    }
    items.sort(key=key_functions[sort_by], reverse=descending)
    return items


@router.get("/history/export")
async def export_history_csv(request: Request, format: str = "csv") -> Response:
    if format.lower() != "csv":
        raise HTTPException(status_code=422, detail="Seul le format CSV est disponible")
    service = services(request)
    rows = [
        history_decision_view(session, advice)
        for session in service.sessions.values()
        for advice in session.advice_history
    ]
    output = io.StringIO()
    fieldnames = (
        list(rows[0])
        if rows
        else [
            "id",
            "hand_number",
            "date",
            "street",
            "final_advice",
            "chosen_action",
            "ev_difference",
            "hand_result",
        ]
    )
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        serializable = {
            key: ";".join(value) if isinstance(value, list) else value for key, value in row.items()
        }
        writer.writerow(serializable)
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="historique-poker-ia.csv"'},
    )


def _find_advice(service: AppServices, advice_id: str) -> tuple[PokerSession, Advice]:
    for session in service.sessions.values():
        advice = next((item for item in session.advice_history if item.id == advice_id), None)
        if advice is not None:
            return session, advice
    raise HTTPException(status_code=404, detail="Décision introuvable")


@router.get("/history/{advice_id}")
async def history_detail(advice_id: str, request: Request) -> dict[str, Any]:
    service = services(request)
    session, advice = _find_advice(service, advice_id)
    snapshot = session.decision_snapshots.get(advice_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Instantané de décision introuvable")
    return decision_detail_view(session, advice)


@router.post("/history/{advice_id}/expert-analysis")
async def expert_analysis(
    advice_id: str,
    request: Request,
    trials: int = Query(default=15_000, ge=100, le=100_000),
    seed: int | None = None,
) -> dict[str, Any]:
    service = services(request)
    session, _ = _find_advice(service, advice_id)
    expert = await asyncio.to_thread(session.expert_analysis, advice_id, trials=trials, seed=seed)
    expert.id = advice_id
    expert.actual_action = next(
        item for item in session.advice_history if item.id == advice_id
    ).actual_action
    expert.actual_amount = next(
        item for item in session.advice_history if item.id == advice_id
    ).actual_amount
    expert.result_net = next(
        item for item in session.advice_history if item.id == advice_id
    ).result_net
    return decision_detail_view(session, expert)


def _find_opponent(
    service: AppServices, player_id: str, session_id: str | None
) -> tuple[PokerSession, OpponentModel]:
    candidates = [service.get(session_id)] if session_id else list(service.sessions.values())
    for session in candidates:
        model = session.opponents.get(player_id)
        if model is not None:
            return session, model
    raise HTTPException(status_code=404, detail="Profil adverse introuvable")


@router.get("/opponents")
async def list_opponents(request: Request, session_id: str | None = None) -> list[dict[str, Any]]:
    service = services(request)
    sessions = [service.get(session_id)] if session_id else list(service.sessions.values())
    return [
        opponent_view(session, model)
        for session in sessions
        for model in session.opponents.values()
    ]


@router.get("/opponents/{player_id}")
async def get_opponent(
    player_id: str, request: Request, session_id: str | None = None
) -> dict[str, Any]:
    service = services(request)
    session, model = _find_opponent(service, player_id, session_id)
    return opponent_view(session, model)


@router.patch("/opponents/{player_id}")
async def patch_opponent(
    player_id: str,
    payload: OpponentPatch,
    request: Request,
    session_id: str | None = None,
) -> dict[str, Any]:
    service = services(request)
    session, _ = _find_opponent(service, player_id, session_id)
    model = session.patch_opponent(player_id, payload)
    service.persistence.enqueue_opponent(session.id, player_id, model.model_dump(mode="json"))
    service.save(session)
    return opponent_view(session, model)


@router.post("/opponents/{player_id}/reset")
async def reset_opponent(
    player_id: str, request: Request, session_id: str | None = None
) -> dict[str, Any]:
    service = services(request)
    session, _ = _find_opponent(service, player_id, session_id)
    model = session.reset_opponent(player_id)
    service.persistence.enqueue_opponent(session.id, player_id, model.model_dump(mode="json"))
    service.save(session)
    return opponent_view(session, model)


@router.post("/opponents/merge")
async def merge_opponents(
    payload: OpponentMerge, request: Request, session_id: str | None = None
) -> dict[str, Any]:
    service = services(request)
    session: PokerSession | None
    if session_id:
        session = service.get(session_id)
    else:
        session = next(
            (
                candidate
                for candidate in service.sessions.values()
                if payload.source_id in candidate.opponents
                and payload.target_id in candidate.opponents
            ),
            None,
        )
        if session is None:
            raise HTTPException(status_code=404, detail="Les profils ne partagent aucune session")
    target = session.merge_opponents(payload.source_id, payload.target_id)
    service.persistence.enqueue_opponent(
        session.id, target.player_id, target.model_dump(mode="json")
    )
    service.save(session)
    return opponent_view(session, target)


@router.get("/opponents/{player_id}/export")
async def export_opponent(
    player_id: str, request: Request, session_id: str | None = None
) -> dict[str, Any]:
    session, model = _find_opponent(services(request), player_id, session_id)
    return {"schema_version": 1, "session_id": session.id, "profile": model.model_dump(mode="json")}


@router.post("/opponents/import")
async def import_opponent(
    payload: dict[str, Any], request: Request, session_id: str | None = None
) -> dict[str, Any]:
    service = services(request)
    raw = payload.get("profile", payload)
    model = OpponentModel.model_validate(raw)
    session = (
        service.get(session_id)
        if session_id
        else next(
            (
                candidate
                for candidate in service.sessions.values()
                if model.player_id in candidate.opponents
            ),
            None,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Aucune session ne contient ce joueur")
    replace_existing = bool(payload.get("replace_existing", True))
    if model.player_id not in session.opponents and not replace_existing:
        raise HTTPException(status_code=409, detail="Ce joueur n'existe pas dans la session")
    try:
        model = session.import_opponent(model)
    except PokerRuleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    service.persistence.enqueue_opponent(session.id, model.player_id, model.model_dump(mode="json"))
    service.save(session)
    return opponent_view(session, model)


@router.get("/sessions/{session_id}/export")
@router.get("/export/{session_id}")
async def export_session(session_id: str, request: Request) -> dict[str, Any]:
    return deepcopy(services(request).get(session_id).export())


@router.get("/sessions/{session_id}/hands/{hand_id}/export")
async def export_hand(session_id: str, hand_id: str, request: Request) -> dict[str, Any]:
    session = services(request).get(session_id)
    candidates = [*session.archived_hands, session.engine.export()]
    hand = next((payload for payload in candidates if payload["hand_id"] == hand_id), None)
    if hand is None:
        raise HTTPException(status_code=404, detail="Main introuvable")
    return {"schema_version": 1, "session_id": session.id, "hand": deepcopy(hand)}


@router.post("/sessions/{session_id}/save")
async def save_session(session_id: str, request: Request) -> dict[str, Any]:
    service = services(request)
    session = service.get(session_id)
    service.save(session)
    return {"saved": True, "saved_at": datetime.now(UTC)}


@router.post("/import")
async def import_session(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    service = services(request)
    raw = payload.get("data", payload)
    replace_existing = bool(payload.get("replace_existing", False))
    try:
        session = PokerSession.restore(raw)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Export de session invalide: {exc}") from exc
    if session.id in service.sessions and not replace_existing:
        raise HTTPException(status_code=409, detail="Cette session existe déjà")
    service.sessions[session.id] = session
    service.locks[session.id] = asyncio.Lock()
    service.save(session)
    return {"imported": True, "session_id": session.id}


@router.post("/sessions/{session_id}/exit")
@router.post("/exit/{session_id}")
async def exit_table(session_id: str, payload: ExitRequest, request: Request) -> dict[str, Any]:
    service = services(request)
    session = service.get(session_id)
    if payload.save:
        service.save(session)
    return exit_report_view(session)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, request: Request) -> None:
    service = services(request)
    service.get(session_id)
    del service.sessions[session_id]
    service.locks.pop(session_id, None)
    service.persistence.enqueue_delete_session(session_id)


@router.delete("/data", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_data(request: Request) -> None:
    service = services(request)
    service.sessions.clear()
    service.locks.clear()
    service.persistence.enqueue_delete_all()


def make_lifespan(database: Database | None = None) -> Any:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = AppServices(database)
        await app.state.services.start()
        try:
            yield
        finally:
            await app.state.services.stop()

    return lifespan


def install_api(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://127.0.0.1", "http://localhost:5173"],
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.exception_handler(PokerRuleError)
    async def poker_rule_error(_request: Request, exc: PokerRuleError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc), "error": "poker_rule"})
