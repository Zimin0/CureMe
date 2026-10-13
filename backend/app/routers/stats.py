"""Приём агрегированных заходов. Публичный адрес без входа: считаем только числа, ничего о посетителе не храним."""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import sitestats
from ..db import get_db
from ..ratelimit import client_ip, limiter

router = APIRouter(prefix="/api/stats", tags=["stats"])


class VisitIn(BaseModel):
    path: str = Field("", max_length=200)
    ref: str | None = Field(None, max_length=300)
    utm: str | None = Field(None, max_length=60)


class GoalIn(BaseModel):
    goal: str = Field(max_length=20)


@router.post("/visit", status_code=204)
def visit(body: VisitIn, request: Request, db: Session = Depends(get_db)):
    limiter.hit(f"stats:{client_ip(request)}", limit=60, window=3600)  # адрес в памяти и только на час, в базу не пишем
    sitestats.bump(db, "visit", "")
    sitestats.bump(db, "page", sitestats.safe_path(body.path))
    if ref := sitestats.referrer_host(body.ref, request.url.hostname):
        sitestats.bump(db, "ref", ref)
    if utm := sitestats.clean_utm(body.utm):
        sitestats.bump(db, "utm", utm)
    return Response(status_code=204)


@router.post("/goal", status_code=204)
def goal(body: GoalIn, request: Request, db: Session = Depends(get_db)):
    limiter.hit(f"stats-goal:{client_ip(request)}", limit=60, window=3600)
    if body.goal in sitestats.GOALS:
        sitestats.bump(db, "goal", body.goal)
    return Response(status_code=204)
