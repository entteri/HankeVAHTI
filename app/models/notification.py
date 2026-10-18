from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationRun(Base):
    """One durable notification execution, including empty-result executions."""

    __tablename__ = "notification_runs"
    __table_args__ = (
        UniqueConstraint("run_key", name="uq_notification_runs_run_key"),
        CheckConstraint(
            "status IN ('IMPORTING', 'EVALUATING', 'READY', 'ATTEMPTING', 'SENT', 'FAILED', 'UNCERTAIN')",
            name="ck_notification_runs_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="IMPORTING")
    phase: Mapped[str] = mapped_column(String(30), nullable=False, default="import")
    next_run_at: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class NotificationHistory(Base):
    """Durable per-project notification queue and final delivery history."""

    __tablename__ = "notification_history"
    __table_args__ = (
        UniqueConstraint("funding_call_id", name="uq_notification_history_funding_call_id"),
        CheckConstraint(
            "status IN ('PENDING_EVALUATION', 'NOT_SELECTED', 'READY', 'ATTEMPTING', 'SENT', 'FAILED', 'UNCERTAIN')",
            name="ck_notification_history_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    funding_call_id: Mapped[int] = mapped_column(
        ForeignKey("funding_calls.id", ondelete="CASCADE"), nullable=False,
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("notification_runs.id", ondelete="CASCADE"), nullable=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING_EVALUATION")
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
    )
