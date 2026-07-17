from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, delete, event, select
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def data_directory() -> Path:
    configured = os.environ.get("POKER_IA_DATA_DIR")
    path = (
        Path(configured).expanduser().resolve()
        if configured
        else Path(__file__).resolve().parents[3] / "data"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


class Base(AsyncAttrs, DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class HandRow(Base):
    __tablename__ = "hands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    hand_number: Mapped[int]
    payload_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventRow(Base):
    __tablename__ = "hand_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hand_id: Mapped[str] = mapped_column(ForeignKey("hands.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int]
    payload_json: Mapped[str] = mapped_column(Text)


class AdviceRow(Base):
    __tablename__ = "advice_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    hand_id: Mapped[str] = mapped_column(String(36), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OpponentRow(Base):
    __tablename__ = "opponents"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or data_directory() / "poker_ia.sqlite3").resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: AsyncEngine = create_async_engine(
            f"sqlite+aiosqlite:///{self.path.as_posix()}"
        )
        event.listen(self.engine.sync_engine, "connect", self._configure_sqlite)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def _configure_sqlite(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    async def upsert_session(self, payload: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        session_id = str(payload["id"])
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        async with self.sessions() as session:
            row = await session.get(SessionRow, session_id)
            if row is None:
                row = SessionRow(
                    id=session_id,
                    name=str(payload["name"]),
                    payload_json=encoded,
                    created_at=datetime.fromisoformat(str(payload["created_at"])),
                    updated_at=now,
                )
                session.add(row)
            else:
                row.name = str(payload["name"])
                row.payload_json = encoded
                row.updated_at = now
            await session.flush()
            engine_payload = payload["engine"]
            hand_id = str(engine_payload["hand_id"])
            hand_row = await session.get(HandRow, hand_id)
            hand_encoded = json.dumps(engine_payload, ensure_ascii=False, separators=(",", ":"))
            if hand_row is None:
                hand_row = HandRow(
                    id=hand_id,
                    session_id=session_id,
                    hand_number=int(engine_payload["hand_number"]),
                    payload_json=hand_encoded,
                    updated_at=now,
                )
                session.add(hand_row)
            else:
                hand_row.payload_json = hand_encoded
                hand_row.updated_at = now
            for event_payload in engine_payload["events"]:
                event_id = str(event_payload["id"])
                event_row = await session.get(EventRow, event_id)
                event_encoded = json.dumps(event_payload, ensure_ascii=False, separators=(",", ":"))
                if event_row is None:
                    session.add(
                        EventRow(
                            id=event_id,
                            hand_id=hand_id,
                            sequence=int(event_payload["sequence"]),
                            payload_json=event_encoded,
                        )
                    )
                else:
                    event_row.payload_json = event_encoded
            await session.commit()

    async def upsert_advice(self, session_id: str, payload: dict[str, Any]) -> None:
        advice_id = str(payload["id"])
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        async with self.sessions() as session:
            row = await session.get(AdviceRow, advice_id)
            if row is None:
                session.add(
                    AdviceRow(
                        id=advice_id,
                        session_id=session_id,
                        hand_id=str(payload["hand_id"]),
                        payload_json=encoded,
                        created_at=datetime.fromisoformat(str(payload["created_at"])),
                    )
                )
            else:
                row.payload_json = encoded
            await session.commit()

    async def upsert_opponent(
        self, session_id: str, player_id: str, payload: dict[str, Any]
    ) -> None:
        key = f"{session_id}:{player_id}"
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        async with self.sessions() as session:
            row = await session.get(OpponentRow, key)
            if row is None:
                session.add(
                    OpponentRow(
                        key=key,
                        session_id=session_id,
                        player_id=player_id,
                        payload_json=encoded,
                        updated_at=datetime.now(UTC),
                    )
                )
            else:
                row.payload_json = encoded
                row.updated_at = datetime.now(UTC)
            await session.commit()

    async def load_sessions(self) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            rows = (
                await session.scalars(select(SessionRow).order_by(SessionRow.updated_at.desc()))
            ).all()
            return [json.loads(row.payload_json) for row in rows]

    async def delete_session(self, session_id: str) -> None:
        async with self.sessions() as session:
            await session.execute(delete(SessionRow).where(SessionRow.id == session_id))
            await session.commit()

    async def delete_all(self) -> None:
        async with self.sessions() as session:
            for model in (EventRow, AdviceRow, OpponentRow, HandRow, SessionRow):
                await session.execute(delete(model))
            await session.commit()
