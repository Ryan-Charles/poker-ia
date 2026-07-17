from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from app.persistence.database import Database


@dataclass(slots=True)
class WriteJob:
    kind: Literal["session", "advice", "opponent", "delete_session", "delete_all"]
    payload: dict[str, Any]
    attempts: int = 0
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid4())


class PersistenceQueue:
    """File en mémoire: aucune mutation de table n'attend SQLite."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.queue: asyncio.Queue[WriteJob] = asyncio.Queue()
        self.worker: asyncio.Task[None] | None = None
        self.last_error: str | None = None
        self.saved_jobs = 0
        self.failed_attempts = 0
        self.spool_directory = self.database.path.parent / ".poker_ia_pending"

    async def start(self) -> None:
        await self.database.initialize()
        self.spool_directory.mkdir(parents=True, exist_ok=True)
        for path in self.spool_directory.glob("*.json"):
            try:
                raw = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
                self.queue.put_nowait(WriteJob(**raw))
            except (OSError, ValueError, TypeError):
                self.last_error = f"Écriture différée illisible conservée: {path.name}"
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._run(), name="poker-ia-sqlite-writer")

    async def stop(self) -> None:
        try:
            await asyncio.wait_for(self.queue.join(), timeout=10.0)
        except TimeoutError:
            self.last_error = "La file SQLite n'a pas pu être vidée avant l'arrêt"
        if self.worker is not None:
            self.worker.cancel()
            with suppress(asyncio.CancelledError):
                await self.worker
        await self.database.close()

    def enqueue_session(self, payload: dict[str, Any]) -> None:
        self.queue.put_nowait(WriteJob("session", payload))

    def enqueue_advice(self, session_id: str, payload: dict[str, Any]) -> None:
        self.queue.put_nowait(WriteJob("advice", {"session_id": session_id, "data": payload}))

    def enqueue_opponent(self, session_id: str, player_id: str, payload: dict[str, Any]) -> None:
        self.queue.put_nowait(
            WriteJob(
                "opponent", {"session_id": session_id, "player_id": player_id, "data": payload}
            )
        )

    def enqueue_delete_session(self, session_id: str) -> None:
        self.queue.put_nowait(WriteJob("delete_session", {"session_id": session_id}))

    def enqueue_delete_all(self) -> None:
        self.queue.put_nowait(WriteJob("delete_all", {}))

    @property
    def status(self) -> Literal["saved", "pending", "warning"]:
        if self.last_error is not None:
            return "warning"
        return "pending" if self.queue.qsize() else "saved"

    async def _run(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                await self._spool(job)
                await self._execute(job)
            except Exception as exc:  # la file doit survivre à toute panne SQLite
                self.failed_attempts += 1
                self.last_error = f"Sauvegarde différée: {type(exc).__name__}: {exc}"
                job.attempts += 1
                await asyncio.sleep(min(5.0, 0.05 * 2 ** min(job.attempts, 10)))
                self.queue.put_nowait(job)
            else:
                self.saved_jobs += 1
                await self._remove_spool(job)
                if self.queue.qsize() == 0:
                    self.last_error = None
            finally:
                self.queue.task_done()

    def _spool_path(self, job: WriteJob) -> Path:
        return self.spool_directory / f"{job.id}.json"

    async def _spool(self, job: WriteJob) -> None:
        path = self._spool_path(job)
        if path.exists():
            return
        payload = {
            "kind": job.kind,
            "payload": job.payload,
            "attempts": job.attempts,
            "id": job.id,
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        temporary = path.with_suffix(".tmp")
        await asyncio.to_thread(temporary.write_text, encoded, encoding="utf-8")
        await asyncio.to_thread(temporary.replace, path)

    async def _remove_spool(self, job: WriteJob) -> None:
        path = self._spool_path(job)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    async def _execute(self, job: WriteJob) -> None:
        if job.kind == "session":
            await self.database.upsert_session(job.payload)
        elif job.kind == "advice":
            await self.database.upsert_advice(job.payload["session_id"], job.payload["data"])
        elif job.kind == "opponent":
            await self.database.upsert_opponent(
                job.payload["session_id"], job.payload["player_id"], job.payload["data"]
            )
        elif job.kind == "delete_session":
            await self.database.delete_session(job.payload["session_id"])
        else:
            await self.database.delete_all()
