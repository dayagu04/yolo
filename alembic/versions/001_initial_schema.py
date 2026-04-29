"""初始数据库架构 - alerts / cameras / users 三表

Revision ID: 001_initial
Revises: None
Create Date: 2026-04-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # alerts 表
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("person_count", sa.Integer(), nullable=False),
        sa.Column("new_track_ids", sa.JSON(), nullable=True),
        sa.Column("screenshot_path", sa.String(512), nullable=True),
        sa.Column("message", sa.String(512), nullable=True),
        sa.Column("level", sa.Enum("low", "medium", "high"), server_default="high"),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_timestamp", "alerts", ["timestamp"])
    op.create_index("ix_alerts_camera_id", "alerts", ["camera_id"])
    op.create_index("ix_alerts_level", "alerts", ["level"])

    # cameras 表
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("status", sa.Enum("online", "offline", "error"), server_default="offline"),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # users 表
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("admin", "operator", "viewer"), server_default="viewer", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("cameras")
    op.drop_table("alerts")
