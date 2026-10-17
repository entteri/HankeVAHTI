
"""Save and retrieve application drafts."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApplicationDraft


def list_application_drafts(
    session: Session,
    funding_call_id: int,
) -> list[ApplicationDraft]:
    """Return drafts for one funding call, newest updated first."""
    statement = (
        select(ApplicationDraft)
        .where(ApplicationDraft.funding_call_id == funding_call_id)
        .order_by(ApplicationDraft.updated_at.desc(), ApplicationDraft.id.desc())
    )
    return list(session.scalars(statement).all())


def save_application_draft(
    session: Session,
    funding_call_id: int,
    title: str,
    content: str,
    draft_id: int | None = None,
) -> ApplicationDraft:
    """Create a draft or update an existing draft belonging to the given call."""
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Anna hakemusluonnokselle otsikko.")

    if draft_id is None:
        draft = ApplicationDraft(
            funding_call_id=funding_call_id,
            title=clean_title,
            content=content,
        )
        session.add(draft)
    else:
        draft = session.scalar(
            select(ApplicationDraft).where(
                ApplicationDraft.id == draft_id,
                ApplicationDraft.funding_call_id == funding_call_id,
            )
        )
        if draft is None:
            raise ValueError("Hakemusluonnosta ei löytynyt tälle rahoitushaulle.")
        draft.title = clean_title
        draft.content = content
        draft.updated_at = datetime.now(timezone.utc)

    session.commit()
    session.refresh(draft)
    return draft
