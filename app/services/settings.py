"""Testikäyttöön tarkoitettu tuotujen hankkeiden tyhjennys."""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Evaluation, FundingCall, Participation


def funding_call_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(FundingCall)) or 0


def delete_all_funding_calls(session: Session) -> int:
    """Poista hankkeet ja niiden päätökset yhdessä transaktiossa."""
    try:
        count = funding_call_count(session)
        session.execute(delete(Participation))
        session.execute(delete(Evaluation))
        session.execute(delete(FundingCall))
        session.commit()
        return count
    except Exception:
        session.rollback()
        raise
