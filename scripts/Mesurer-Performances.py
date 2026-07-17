from __future__ import annotations

import asyncio
import ctypes
import gc
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTION_SAMPLES = 500
CARD_SAMPLES = 500
LONG_RUN_CYCLES = 2_000
HISTORY_DECISIONS = 5_000
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.engine.session import PokerSession  # noqa: E402
from app.models import (  # noqa: E402
    ActionKind,
    ActionRequest,
    AnalysisLevel,
    PlayerConfig,
    SessionCreate,
)
from app.persistence.database import Database  # noqa: E402
from app.persistence.queue import PersistenceQueue  # noqa: E402
from app.presentation import history_decision_view  # noqa: E402


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("page_fault_count", wintypes.DWORD),
        ("peak_working_set_size", ctypes.c_size_t),
        ("working_set_size", ctypes.c_size_t),
        ("quota_peak_paged_pool_usage", ctypes.c_size_t),
        ("quota_paged_pool_usage", ctypes.c_size_t),
        ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
        ("quota_non_paged_pool_usage", ctypes.c_size_t),
        ("pagefile_usage", ctypes.c_size_t),
        ("peak_pagefile_usage", ctypes.c_size_t),
        ("private_usage", ctypes.c_size_t),
    ]


def process_memory_kib() -> dict[str, float]:
    if sys.platform != "win32":
        return {"working_set": 0.0, "private": 0.0, "peak_working_set": 0.0}
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    process = kernel32.GetCurrentProcess()
    success = psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
    if not success:
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        "working_set": counters.working_set_size / 1024,
        "private": counters.private_usage / 1024,
        "peak_working_set": counters.peak_working_set_size / 1024,
    }


def phase(label: str) -> None:
    print(f"Mesure: {label}", file=sys.stderr, flush=True)


def configuration(player_count: int) -> SessionCreate:
    players = [
        PlayerConfig(
            id="hero" if index == 0 else f"p{index + 1}",
            name="Ryanchl" if index == 0 else f"Joueur {index + 1}",
            seat=index + 1,
            stack=10_000,
        )
        for index in range(player_count)
    ]
    if player_count == 2:
        button, small, big = "hero", "hero", "p2"
    else:
        button, small, big = (
            f"p{player_count - 2}",
            f"p{player_count - 1}",
            f"p{player_count}",
        )
    return SessionCreate(
        players=players,
        small_blind=50,
        big_blind=100,
        button_player_id=button,
        small_blind_player_id=small,
        big_blind_player_id=big,
    )


def percentiles(samples: list[float], *, unit: str = "ms") -> dict[str, Any]:
    ordered = sorted(samples)
    p95_index = max(0, min(len(ordered) - 1, round(0.95 * (len(ordered) - 1))))
    return {
        "samples": len(samples),
        "unit": unit,
        "p50": round(statistics.median(ordered), 4),
        "p95": round(ordered[p95_index], 4),
        "max": round(ordered[-1], 4),
    }


def timed(call: Callable[[], Any]) -> float:
    started = time.perf_counter_ns()
    call()
    return (time.perf_counter_ns() - started) / 1_000_000


def action_and_card_benchmarks() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    action_session = PokerSession(configuration(2))
    action_samples: list[float] = []
    for _ in range(ACTION_SAMPLES):
        action_samples.append(
            timed(lambda: action_session.take_action(ActionRequest(action=ActionKind.CALL)))
        )
        action_session.undo()

    card_session = PokerSession(configuration(2))
    card_samples: list[float] = []
    for _ in range(CARD_SAMPLES):
        card_samples.append(timed(lambda: card_session.engine.set_card("hero_1", "As")))
        card_session.engine.clear_card("hero_1")

    memory_session = PokerSession(configuration(2))
    gc.collect()
    before = process_memory_kib()
    observed_peak = before["working_set"]
    for index in range(LONG_RUN_CYCLES):
        memory_session.take_action(ActionRequest(action=ActionKind.CALL))
        memory_session.undo()
        if index % 100 == 0:
            observed_peak = max(observed_peak, process_memory_kib()["working_set"])
    gc.collect()
    after = process_memory_kib()
    memory = {
        "cycles": LONG_RUN_CYCLES,
        "working_set_delta_kib": round(after["working_set"] - before["working_set"], 2),
        "private_delta_kib": round(after["private"] - before["private"], 2),
        "observed_peak_working_set_kib": round(observed_peak, 2),
        "process_peak_working_set_kib": round(after["peak_working_set"], 2),
        "events_after": len(memory_session.engine.events),
    }
    return percentiles(action_samples), percentiles(card_samples), memory


def strategy_benchmark(player_count: int) -> dict[str, Any]:
    session = PokerSession(configuration(player_count))
    session.engine.set_card("hero_1", "As")
    session.engine.set_card("hero_2", "Kd")
    cold_samples = [
        timed(
            lambda seed=seed: session.advisor.advise(
                session_id=session.id,
                config=session.config,
                state=session.engine.state,
                opponents=session.opponents,
                level=AnalysisLevel.FAST,
                trials=700,
                seed=seed,
            )
        )
        for seed in range(10, 20)
    ]
    session.advisor.advise(
        session_id=session.id,
        config=session.config,
        state=session.engine.state,
        opponents=session.opponents,
        level=AnalysisLevel.FAST,
        trials=700,
        seed=777,
    )
    warm_samples = [
        timed(
            lambda: session.advisor.advise(
                session_id=session.id,
                config=session.config,
                state=session.engine.state,
                opponents=session.opponents,
                level=AnalysisLevel.FAST,
                trials=700,
                seed=777,
            )
        )
        for _ in range(100)
    ]
    return {
        "players": player_count,
        "trials": 700,
        "cold": percentiles(cold_samples),
        "cache_hit": percentiles(warm_samples),
        "cache_entries": session.advisor.cache_entries,
        "cache_hits": session.advisor.cache_hits,
    }


def history_benchmark() -> dict[str, Any]:
    session = PokerSession(configuration(2))
    session.engine.set_card("hero_1", "As")
    session.engine.set_card("hero_2", "Kd")
    template = session.generate_advice(trials=100, seed=5)
    snapshot = session.decision_snapshots[template.id]
    decisions = [
        template.model_copy(deep=True, update={"id": f"benchmark-{index}"})
        for index in range(HISTORY_DECISIONS)
    ]
    session.advice_history = decisions
    session.decision_snapshots = {decision.id: snapshot for decision in decisions}
    gc.collect()
    before = process_memory_kib()
    started = time.perf_counter()
    rows = [history_decision_view(session, decision) for decision in decisions]
    duration_ms = (time.perf_counter() - started) * 1_000
    with_rows = process_memory_kib()
    row_count = len(rows)
    del rows
    gc.collect()
    released = process_memory_kib()
    return {
        "decisions": row_count,
        "projection_ms": round(duration_ms, 2),
        "working_set_delta_with_rows_kib": round(
            with_rows["working_set"] - before["working_set"], 2
        ),
        "private_delta_with_rows_kib": round(with_rows["private"] - before["private"], 2),
        "working_set_after_release_kib": round(released["working_set"], 2),
        "frontend_initial_window": 200,
        "live_panel_window": 100,
    }


def queue_benchmark() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="poker-ia-bench-") as directory:
        database = Database(Path(directory) / "benchmark.sqlite3")
        queue = PersistenceQueue(database)
        payload = PokerSession(configuration(2)).export()
        samples = [timed(lambda: queue.enqueue_session(payload)) for _ in range(5_000)]
        queued = queue.queue.qsize()
        asyncio.run(database.close())
    return {**percentiles(samples), "queued_without_waiting": queued}


def main() -> None:
    phase("actions, cartes et mémoire longue")
    action, card, long_run_memory = action_and_card_benchmarks()
    phase("stratégie heads-up")
    strategy_heads_up = strategy_benchmark(2)
    phase("stratégie six joueurs")
    strategy_six_players = strategy_benchmark(6)
    phase("historique de 5 000 décisions")
    history = history_benchmark()
    phase("file de persistance")
    persistence_enqueue = queue_benchmark()
    report = {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "inconnu"),
            "logical_processors": os.cpu_count(),
        },
        "action": action,
        "card_selection_engine": card,
        "long_run_memory": long_run_memory,
        "strategy_heads_up": strategy_heads_up,
        "strategy_six_players": strategy_six_players,
        "history": history,
        "persistence_enqueue": persistence_enqueue,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
