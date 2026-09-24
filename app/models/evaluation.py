from datetime import datetime, timezone
from enum import Enum as PythonEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.funding_call import FundingCall


class EvaluationStatus(str, PythonEnum):
    NEW = "NEW"
    UNDER_REVIEW = "UNDER_REVIEW"
    INTERESTING = "INTERESTING"
    PARTICIPATE = "PARTICIPATE"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("funding_call_id", name="uq_evaluations_funding_call_id"),
        CheckConstraint("suitability_score IS NULL OR (suitability_score >= 0 AND suitability_score <= 100)", name="ck_evaluations_score_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    funding_call_id: Mapped[int] = mapped_column(ForeignKey("funding_calls.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[EvaluationStatus] = mapped_column(Enum(EvaluationStatus, native_enum=False, create_constraint=True, name="evaluation_status"), nullable=False, default=EvaluationStatus.NEW)
    suitability_score: Mapped[int | None] = mapped_column(Integer)
    suitability_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    funding_call: Mapped["FundingCall"] = relationship(back_populates="evaluation")
