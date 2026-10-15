from sqlalchemy import Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HaeavustuksiaSearchCriteria(Base):
    """Yhden käyttäjän tallennetut Haeavustuksia-hakujen rajaukset."""

    __tablename__ = "haeavustuksia_search_criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    grant_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    show_future: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    show_ongoing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    authorities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
