"""Manuaalisen tuonnin REST-rajapinta."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.imports import run_imports

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("/run")
def run_import(db: Session = Depends(get_db)) -> dict[str, dict[str, int]]:
    try:
        return run_imports(db)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.exception("Tietolähteiden tuonti epäonnistui")
        raise HTTPException(status_code=502, detail="Tietolähteiden tuonti epäonnistui") from exc
