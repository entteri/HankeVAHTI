"""Hankkeiden luku- ja tilarajapinta."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import EvaluationStatus
from app.services.funding_calls import FundingCallSort, get_funding_call, list_funding_calls, set_funding_call_status

router = APIRouter(prefix="/api/funding-calls", tags=["funding-calls"])


class StatusUpdate(BaseModel):
    status: EvaluationStatus


@router.get("")
def funding_calls(
    status: EvaluationStatus | None = None,
    search: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: FundingCallSort = FundingCallSort.DEFAULT,
    db: Session = Depends(get_db),
) -> dict:
    calls, total = list_funding_calls(db, status=status, search=search, page=page, page_size=page_size, sort=sort)
    return {"items": [asdict(call) for call in calls], "total": total, "page": page, "page_size": page_size}


@router.get("/{call_id}")
def funding_call(call_id: int, db: Session = Depends(get_db)) -> dict:
    call = get_funding_call(db, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Hanketta ei löytynyt")
    return asdict(call)


@router.patch("/{call_id}/status")
def update_status(call_id: int, update: StatusUpdate, db: Session = Depends(get_db)) -> dict:
    call = set_funding_call_status(db, call_id, update.status)
    if call is None:
        raise HTTPException(status_code=404, detail="Hanketta ei löytynyt")
    return asdict(call)
