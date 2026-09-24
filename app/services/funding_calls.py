"""Hankkeiden selaus ja osallistumispäätökset."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Evaluation, EvaluationStatus, FundingCall, Participation, ParticipationStage


@dataclass(frozen=True)
class FundingCallView:
    id: int
    source: str
    source_id: str
    call_identifier: str | None
    title: str
    description: str | None
    fund: str | None
    category: str | None
    source_url: str | None
    application_start_date: date | None
    application_end_date: date | None
    status: EvaluationStatus
    suitability_score: int | None
    suitability_summary: str | None
    participation_stage: ParticipationStage | None
    responsible_person: str | None
    next_action: str | None


def _view(call: FundingCall) -> FundingCallView:
    evaluation = call.evaluation
    participation = call.participation
    return FundingCallView(
        id=call.id,
        source=call.source,
        source_id=call.source_id,
        call_identifier=call.call_identifier,
        title=call.title,
        description=call.description,
        fund=call.fund,
        category=call.category,
        source_url=(
            f"https://eura2021.fi/hakuilmoitukset/hakuilmoitus/{call.source_id}/"
            if call.source == "EURA" else call.source_url
        ),
        application_start_date=call.application_start_date,
        application_end_date=call.application_end_date,
        status=evaluation.status if evaluation else EvaluationStatus.NEW,
        suitability_score=evaluation.suitability_score if evaluation else None,
        suitability_summary=evaluation.suitability_summary if evaluation else None,
        participation_stage=participation.stage if participation else None,
        responsible_person=participation.responsible_person if participation else None,
        next_action=participation.next_action if participation else None,
    )


def _filters(status: EvaluationStatus | None, search: str) -> list:
    filters = []
    if status is EvaluationStatus.NEW:
        filters.append(or_(Evaluation.status == EvaluationStatus.NEW, Evaluation.id.is_(None)))
    elif status is not None:
        filters.append(Evaluation.status == status)
    search = search.strip()
    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                FundingCall.title.ilike(pattern),
                FundingCall.call_identifier.ilike(pattern),
                FundingCall.source_id.ilike(pattern),
            )
        )
    return filters


def list_funding_calls(
    session: Session,
    *,
    status: EvaluationStatus | None = None,
    search: str = "",
    page: int = 1,
    page_size: int = 20,
    ongoing_only: bool = False,
) -> tuple[list[FundingCallView], int]:
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError("Virheellinen sivunumero tai sivukoko")
    filters = _filters(status, search)
    if ongoing_only:
        filters.extend((
            Evaluation.status == EvaluationStatus.PARTICIPATE,
            Participation.stage.not_in((ParticipationStage.REJECTED, ParticipationStage.COMPLETED)),
        ))
    total = session.scalar(
        select(func.count(FundingCall.id))
        .outerjoin(Evaluation)
        .outerjoin(Participation)
        .where(*filters)
    ) or 0
    calls = session.scalars(
        select(FundingCall)
        .outerjoin(Evaluation)
        .outerjoin(Participation)
        .where(*filters)
        .options(selectinload(FundingCall.evaluation), selectinload(FundingCall.participation))
        .order_by(FundingCall.created_at.desc(), FundingCall.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_view(call) for call in calls], total


def get_funding_call(session: Session, call_id: int) -> FundingCallView | None:
    call = session.scalar(
        select(FundingCall)
        .where(FundingCall.id == call_id)
        .options(selectinload(FundingCall.evaluation), selectinload(FundingCall.participation))
    )
    return _view(call) if call else None


def set_funding_call_status(session: Session, call_id: int, status: EvaluationStatus) -> FundingCallView | None:
    call = session.get(FundingCall, call_id)
    if call is None:
        return None
    if call.evaluation is None:
        call.evaluation = Evaluation(status=status)
    else:
        call.evaluation.status = status
    if status is EvaluationStatus.PARTICIPATE and call.participation is None:
        call.participation = Participation(stage=ParticipationStage.NOT_STARTED)
    session.commit()
    return get_funding_call(session, call_id)


def dashboard_counts(session: Session) -> dict[str, int]:
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent = session.scalar(
        select(func.count(FundingCall.id)).where(FundingCall.created_at >= week_ago)
    ) or 0
    new = session.scalar(
        select(func.count(FundingCall.id))
        .outerjoin(Evaluation)
        .where(or_(Evaluation.status == EvaluationStatus.NEW, Evaluation.id.is_(None)))
    ) or 0
    participating = session.scalar(
        select(func.count(Evaluation.id)).where(Evaluation.status == EvaluationStatus.PARTICIPATE)
    ) or 0
    rejected = session.scalar(
        select(func.count(Evaluation.id)).where(Evaluation.status == EvaluationStatus.REJECTED)
    ) or 0
    ongoing = session.scalar(
        select(func.count(Participation.id))
        .join(Evaluation, Evaluation.funding_call_id == Participation.funding_call_id)
        .where(
            Evaluation.status == EvaluationStatus.PARTICIPATE,
            Participation.stage.not_in((ParticipationStage.REJECTED, ParticipationStage.COMPLETED)),
        )
    ) or 0
    return {
        "recent": recent,
        "new": new,
        "participating": participating,
        "rejected": rejected,
        "ongoing": ongoing,
    }
