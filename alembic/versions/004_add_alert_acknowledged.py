"""告警表新增确认字段

Revision ID: 004_add_alert_acknowledged
Revises: 003_add_escalation_and_roi
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_add_alert_acknowledged"
down_revision: Union[str, None] = "003_add_escalation_and_roi"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("acknowledged", sa.Boolean(), server_default=sa.text("0")))
    op.add_column("alerts", sa.Column("acknowledged_by", sa.String(50), nullable=True))
    op.add_column("alerts", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "acknowledged_at")
    op.drop_column("alerts", "acknowledged_by")
    op.drop_column("alerts", "acknowledged")
