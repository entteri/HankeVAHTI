"""Erikseen ajettava pisteytys, joka säilyttää lähdetiedot ja käyttäjän päätökset."""

from collections.abc import Collection
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.evaluators.relevance import evaluate_relevance
from app.models import Evaluation, EvaluationStatus, FundingCall
from app.services.search_profiles import get_relevance_profile


def score_funding_calls(
    session: Session, *, call_ids: Collection[int] | None = None, as_of: date | None = None,
) -> int:
    """Pisteytä päättymättömät haut (myös tulevat ja haut ilman päättymispäivää).

    call_ids rajaa ajon esimerkiksi uusiin/muuttuneisiin hakuihin. None käsittelee
    kaikki päättymättömät haut, riippumatta käyttäjän osallistumispäätöksestä.
    Funktio omistaa transaktion; käyttöliittymä kutsuu sitä omalla sessiolla.
    """
    try:
        profile = get_relevance_profile(session)
        if profile is None or not profile.active:
            raise ValueError("Tallenna relevanssin hakusanat Asetukset-sivulla ennen pisteytystä.")
        today = as_of or datetime.now(ZoneInfo("Europe/Helsinki")).date()
        query = select(FundingCall).where(or_(
            FundingCall.application_end_date.is_(None),
            FundingCall.application_end_date >= today,
        )).options(selectinload(FundingCall.evaluation))
        if call_ids is not None:
            query = query.where(FundingCall.id.in_(call_ids))
        calls = session.scalars(query).all()
        for call in calls:
            result = evaluate_relevance(
                (call.title, call.description, call.fund, call.category),
                profile.keywords, profile.excluded_keywords,
            )
            if call.evaluation is None:
                call.evaluation = Evaluation(status=EvaluationStatus.NEW)
            call.evaluation.suitability_score = result.score
            call.evaluation.suitability_summary = result.summary
        session.commit()
        return len(calls)
    except Exception:
        session.rollback()
        raise
