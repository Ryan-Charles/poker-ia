from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config

from alembic import command
from app.engine.session import PokerSession
from app.models import SessionCreate
from app.persistence.database import Database
from app.persistence.queue import PersistenceQueue

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_initial_migration_adopts_existing_application_database(
    tmp_path: Path,
    make_config: Callable[..., SessionCreate],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "poker_ia.sqlite3"
    database = Database(database_path)
    await database.initialize()
    poker_session = PokerSession(make_config(2))
    await database.upsert_session(poker_session.export())
    await database.close()

    monkeypatch.setenv("POKER_IA_DATA_DIR", str(tmp_path))
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(alembic_config, "head")

    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        persisted = connection.execute("SELECT id FROM sessions").fetchall()
    assert revision == ("0001_initial",)
    assert persisted == [(poker_session.id,)]


@pytest.mark.asyncio
async def test_queue_retry_is_non_blocking_and_loses_no_job(
    tmp_path: Path,
    make_config: Callable[..., SessionCreate],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(tmp_path / "retry.sqlite3")
    queue = PersistenceQueue(database)
    await queue.start()
    session = PokerSession(make_config(3))
    payload = session.export()
    original = database.upsert_session
    attempts = 0

    async def flaky(data: dict[str, Any]) -> None:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise OSError("verrou temporaire simulé")
        await original(data)

    monkeypatch.setattr(database, "upsert_session", flaky)
    started = time.perf_counter()
    queue.enqueue_session(payload)
    assert time.perf_counter() - started < 0.02
    await asyncio.wait_for(queue.queue.join(), timeout=3.0)
    assert attempts == 3
    assert queue.failed_attempts == 2
    assert (await database.load_sessions())[0]["id"] == session.id
    assert not list(queue.spool_directory.glob("*.json"))
    await queue.stop()


@pytest.mark.asyncio
async def test_database_isolated_restore_and_delete(
    tmp_path: Path, make_config: Callable[..., SessionCreate]
) -> None:
    first = Database(tmp_path / "first.sqlite3")
    second = Database(tmp_path / "second.sqlite3")
    await first.initialize()
    await second.initialize()
    session = PokerSession(make_config(2))
    await first.upsert_session(session.export())
    loaded = await first.load_sessions()
    assert PokerSession.restore(loaded[0]).id == session.id
    assert await second.load_sessions() == []
    await first.delete_session(session.id)
    assert await first.load_sessions() == []
    await first.close()
    await second.close()


@pytest.mark.asyncio
async def test_queue_stop_flushes_pending_writes(
    tmp_path: Path, make_config: Callable[..., SessionCreate]
) -> None:
    database = Database(tmp_path / "flush.sqlite3")
    queue = PersistenceQueue(database)
    await queue.start()
    session = PokerSession(make_config(2))
    queue.enqueue_session(session.export())
    await queue.stop()
    verification = Database(tmp_path / "flush.sqlite3")
    await verification.initialize()
    assert (await verification.load_sessions())[0]["id"] == session.id
    await verification.close()
