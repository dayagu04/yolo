"""新增告警升级记录表和 ROI 配置表

Revision ID: 003_add_escalation_and_roi
Revises: 002_add_audit_logs
Create Date: 2026-04-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_add_escalation_and_roi"
down_revision: Union[str, None] = "002_add_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 告警升级记录表
    op.create_table(
        "alert_escalations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("from_level", sa.String(20), nullable=False),
        sa.Column("to_level", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notified", sa.Boolean(), server_default=sa.text("0")),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_escalations_alert_id", "alert_escalations", ["alert_id"])

    # 摄像头 ROI 配置表
    op.create_table(
        "camera_rois",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("roi_type", sa.Enum("intrusion", "loitering", "gathering", "monitoring"),
                  server_default="intrusion", nullable=False),
        sa.Column("polygon", sa.JSON(), nullable=False),
        sa.Column("min_persons", sa.Integer(), server_default=sa.text("1")),
        sa.Column("min_duration_sec", sa.Integer(), server_default=sa.text("0")),
        sa.Column("alert_level", sa.Enum("low", "medium", "high"), server_default="high"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_camera_rois_camera_id", "camera_rois", ["camera_id"])


def downgrade() -> None:
    op.drop_table("camera_rois")
    op.drop_table("alert_escalations")
