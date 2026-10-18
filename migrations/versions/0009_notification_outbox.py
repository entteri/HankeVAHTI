"""Persist notification runs, queued calls, and delivery outcomes.

Revision ID: 0009_notification_outbox
Revises: 0008_notification_history
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_notification_outbox"
down_revision = "0008_notification_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("phase", sa.String(length=30), nullable=False),
        sa.Column("next_run_at", sa.String(length=100), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('IMPORTING', 'EVALUATING', 'READY', 'ATTEMPTING', 'SENT', 'FAILED', 'UNCERTAIN')",
            name="ck_notification_runs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key", name="uq_notification_runs_run_key"),
    )

    with op.batch_alter_table("notification_history") as batch:
        batch.alter_column(
            "notified_at", new_column_name="queued_at",
            existing_type=sa.DateTime(timezone=True), nullable=False,
        )
        batch.add_column(sa.Column("run_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("status", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_notification_history_run_id_notification_runs",
            "notification_runs", ["run_id"], ["id"], ondelete="CASCADE",
        )
        batch.create_check_constraint(
            "ck_notification_history_status",
            "status IN ('PENDING_EVALUATION', 'NOT_SELECTED', 'READY', 'ATTEMPTING', 'SENT', 'FAILED', 'UNCERTAIN')",
        )

    connection = op.get_bind()
    connection.execute(sa.text(
        "UPDATE notification_history SET status = 'SENT', sent_at = queued_at"
    ))
    with op.batch_alter_table("notification_history") as batch:
        batch.alter_column("status", existing_type=sa.String(length=30), nullable=False)


def downgrade() -> None:
    connection = op.get_bind()
    run_count = connection.scalar(sa.text("SELECT count(*) FROM notification_runs")) or 0
    if run_count:
        raise RuntimeError(
            "Cannot downgrade notification outbox while notification run history exists."
        )
    unsent_count = connection.scalar(sa.text(
        "SELECT count(*) FROM notification_history WHERE status != 'SENT'"
    )) or 0
    if unsent_count:
        raise RuntimeError(
            "Cannot downgrade notification outbox while unsent or unresolved notification records exist."
        )

    with op.batch_alter_table("notification_history") as batch:
        batch.drop_constraint("ck_notification_history_status", type_="check")
        batch.drop_constraint("fk_notification_history_run_id_notification_runs", type_="foreignkey")
        batch.drop_column("run_id")
        batch.drop_column("status")
        batch.drop_column("last_error")
        batch.alter_column(
            "sent_at", new_column_name="notified_at",
            existing_type=sa.DateTime(timezone=True), nullable=False,
        )
        batch.drop_column("queued_at")

    op.drop_table("notification_runs")
