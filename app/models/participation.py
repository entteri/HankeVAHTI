from datetime import datetime, timezone
from enum import Enum as PythonEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.funding_call import FundingCall


class ParticipationStage(str, PythonEnum):
    NOT_STARTED = "NOT_STARTED"
    PLANNING = "PLANNING"
    PREPARING_APPLICATION = "PREPARING_APPLICATION"
    WAITING_FOR_DECISION = "WAITING_FOR_DECISION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class Participation(Base):
    __tablename__ = "participations"
    __table_args__ = (UniqueConstraint("funding_call_id", name="uq_participations_funding_call_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    funding_call_id: Mapped[int] = mapped_column(ForeignKey("funding_calls.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[ParticipationStage] = mapped_column(Enum(ParticipationStage, native_enum=False, create_constraint=True, name="participation_stage"), nullable=False, default=ParticipationStage.NOT_STARTED)
    responsible_person: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    funding_call: Mapped["FundingCall"] = relationship(back_populates="participation")
