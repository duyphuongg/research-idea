from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analysis.us_calendar import (
    advice_for,
    PHASE_LABEL,
    load_calendar,
    milestones,
    occurrences,
    phase,
)
from app.api.deps import get_session
from app.api.schemas import CalendarEventOut, CalendarPage
from app.services.calendar_ideas import latest_scores, radar_matches, seed_ideas

router = APIRouter(prefix="/api")


@router.get("/calendar", response_model=CalendarPage)
def get_calendar(
    days: int = Query(120, ge=1, le=400),
    today: date | None = None,
    session: Session = Depends(get_session),
) -> CalendarPage:
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    cfg = load_calendar()
    defs, fulfillment_days, buffer = cfg.events, cfg.fulfillment_days, cfg.ship_buffer_days
    scores = latest_scores(session)
    events = []
    for occ in occurrences(defs, today, days):
        m = milestones(occ, fulfillment_days, buffer)
        current = phase(occ, today, fulfillment_days, buffer)
        events.append(
            CalendarEventOut(
                key=occ.event.key,
                name=occ.event.name,
                type=occ.event.type,
                start=occ.start,
                end=occ.end,
                days_until=(occ.start - today).days,
                phase=current,
                phase_label=PHASE_LABEL[current],
                advice=advice_for(occ, current, today, m),
                note=occ.event.note,
                design_start=m.design_start,
                launch_by=m.launch_by,
                push_from=m.push_from,
                ship_by=m.ship_by,
                order_by=m.order_by,
                theme_words=list(occ.event.theme_words),
                seed_ideas=seed_ideas(session, occ, scores, defs),
                radar_matches=radar_matches(session, occ, scores),
            )
        )
    return CalendarPage(today=today, fulfillment_days=fulfillment_days, events=events)
