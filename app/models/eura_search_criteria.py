from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EuraSearchCriteria(Base):
    """Yhden käyttäjän tallennetut EURA-hakuilmoitusten rajaukset."""

    __tablename__ = "eura_search_criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund: Mapped[str | None] = mapped_column(String(100))
    area: Mapped[str | None] = mapped_column(String(100))
    authority: Mapped[str | None] = mapped_column(String(100))
    regions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    call_identifier: Mapped[str | None] = mapped_column(String(255))
