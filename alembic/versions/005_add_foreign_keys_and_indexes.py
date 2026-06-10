"""添加外键约束和缺失索引

Revision ID: 005
Revises: 004_add_alert_acknowledged
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004_add_alert_acknowledged"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # alerts.camera_id 需可空，才能建立 ON DELETE SET NULL 外键
    op.alter_column("alerts", "camera_id", existing_type=sa.Integer(), nullable=True)

    # 外键约束
    op.create_foreign_key("fk_alerts_camera_id", "alerts", "cameras", ["camera_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_escalations_alert_id", "alert_escalations", "alerts", ["alert_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_rois_camera_id", "camera_rois", "cameras", ["camera_id"], ["id"], ondelete="CASCADE")

    # 缺失索引
    op.create_index("ix_cameras_status", "cameras", ["status"])
    op.create_index("ix_alert_escalations_notified", "alert_escalations", ["notified"])
    op.create_index("ix_camera_rois_enabled", "camera_rois", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_camera_rois_enabled", table_name="camera_rois")
    op.drop_index("ix_alert_escalations_notified", table_name="alert_escalations")
    op.drop_index("ix_cameras_status", table_name="cameras")
    op.drop_constraint("fk_rois_camera_id", "camera_rois", type_="foreignkey")
    op.drop_constraint("fk_escalations_alert_id", "alert_escalations", type_="foreignkey")
    op.drop_constraint("fk_alerts_camera_id", "alerts", type_="foreignkey")
    op.alter_column("alerts", "camera_id", existing_type=sa.Integer(), nullable=False)
