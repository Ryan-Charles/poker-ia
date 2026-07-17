"""Schéma local initial de Poker IA.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # L'application autonome sait initialiser une base vide au premier démarrage.
    # La migration doit donc aussi pouvoir adopter sans perte cette base déjà
    # créée par SQLAlchemy, puis laisser Alembic inscrire sa révision.
    bind = op.get_bind()

    def missing_table(name: str) -> bool:
        return not sa.inspect(bind).has_table(name)

    def ensure_index(name: str, table: str, columns: list[str]) -> None:
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes(table)}
        if name not in indexes:
            op.create_index(name, table, columns)

    if missing_table("sessions"):
        op.create_table(
            "sessions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    ensure_index("ix_sessions_updated_at", "sessions", ["updated_at"])

    if missing_table("hands"):
        op.create_table(
            "hands",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("hand_number", sa.Integer(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    ensure_index("ix_hands_session_id", "hands", ["session_id"])

    if missing_table("hand_events"):
        op.create_table(
            "hand_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("hand_id", sa.String(length=36), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["hand_id"], ["hands.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    ensure_index("ix_hand_events_hand_id", "hand_events", ["hand_id"])

    if missing_table("advice_history"):
        op.create_table(
            "advice_history",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("hand_id", sa.String(length=36), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    ensure_index("ix_advice_history_session_id", "advice_history", ["session_id"])
    ensure_index("ix_advice_history_hand_id", "advice_history", ["hand_id"])
    ensure_index("ix_advice_history_created_at", "advice_history", ["created_at"])

    if missing_table("opponents"):
        op.create_table(
            "opponents",
            sa.Column("key", sa.String(length=120), nullable=False),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("player_id", sa.String(length=64), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("key"),
        )
    ensure_index("ix_opponents_session_id", "opponents", ["session_id"])
    ensure_index("ix_opponents_player_id", "opponents", ["player_id"])


def downgrade() -> None:
    op.drop_table("opponents")
    op.drop_table("advice_history")
    op.drop_table("hand_events")
    op.drop_table("hands")
    op.drop_table("sessions")
