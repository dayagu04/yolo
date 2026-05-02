"""添加告警复合索引优化查询性能

Revision ID: 006
Revises: 005
Create Date: 2026-05-02
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 复合索引：覆盖 query_alerts 的主要查询模式
    # (camera_id, level, timestamp) 支持按摄像头+级别+时间范围筛选并排序
    op.create_index(
        "ix_alerts_cam_level_ts", "alerts",
        ["camera_id", "level", "timestamp"],
    )
    # acknowledged 索引：支持按确认状态筛选
    op.create_index("ix_alerts_acknowledged", "alerts", ["acknowledged"])


def downgrade() -> None:
    op.drop_index("ix_alerts_acknowledged", table_name="alerts")
    op.drop_index("ix_alerts_cam_level_ts", table_name="alerts")
