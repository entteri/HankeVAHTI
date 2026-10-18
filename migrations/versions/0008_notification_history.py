"""Track funding calls included in notifications.

Revision ID: 0008_notification_history
Revises: 0007_multiple_search_criteria
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_notification_history"
down_revision = "0007_multiple_search_criteria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("funding_call_id", sa.Integer(), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["funding_call_id"], ["funding_calls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("funding_call_id", name="uq_notification_history_funding_call_id"),
    )


def downgrade() -> None:
    op.drop_table("notification_history")
