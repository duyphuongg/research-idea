from collections import defaultdict
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.scoring import HISTORY_DAYS
from app.api.deps import get_session
from app.api.schemas import (
    RelatedKeywordOut,
    SignalPoint,
    SignalSeries,
    TrendDetail,
    TrendOut,
    TrendPage,
)
from app.models import Keyword, KeywordRelation, KeywordScore, Seed, TrendSignal

router = APIRouter(prefix="/api")
NEW_DAYS = 7


def _seed_texts(session: Session) -> set[str]:
    return set(session.scalars(select(Seed.keyword)))


def _sparklines(session: Session, keyword_ids: list[int], latest: date) -> dict[int, list[float]]:
    if not keyword_ids:
        return {}
    since = latest - timedelta(days=HISTORY_DAYS - 1)
    rows = session.execute(
        select(KeywordScore.keyword_id, KeywordScore.score)
        .where(
            KeywordScore.keyword_id.in_(keyword_ids),
            KeywordScore.date >= since,
            KeywordScore.date <= latest,
        )
        .order_by(KeywordScore.date)
    )
    out: dict[int, list[float]] = defaultdict(list)
    for keyword_id, score in rows:
        out[keyword_id].append(score)
    return out


def _trend_out(
    score: KeywordScore, keyword: Keyword, seeds: set[str], sparkline: list[float]
) -> TrendOut:
    return TrendOut(
        keyword_id=keyword.id,
        keyword=keyword.text,
        origin=keyword.origin,
        is_pod_relevant=keyword.is_pod_relevant,
        is_seed=keyword.text in seeds,
        is_new=keyword.first_seen_at.date() >= score.date - timedelta(days=NEW_DAYS),
        score=score.score,
        demand=score.demand,
        momentum=score.momentum,
        competition=score.competition,
        growth=score.growth,
        sources=list(score.sources or []),
        sources_rising=score.sources_rising,
        sparkline=sparkline,
    )


@router.get("/trends", response_model=TrendPage)
def list_trends(
    source: str | None = None,
    origin: Literal["seed", "discovered"] | None = None,
    pod_only: bool = True,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> TrendPage:
    latest = session.scalar(select(func.max(KeywordScore.date)))
    if latest is None:
        return TrendPage(date=None, items=[])
    rows = session.execute(
        select(KeywordScore, Keyword)
        .join(Keyword, Keyword.id == KeywordScore.keyword_id)
        .where(KeywordScore.date == latest)
    ).all()
    selected = [
        (score, keyword)
        for score, keyword in rows
        if (not pod_only or keyword.is_pod_relevant)
        and (origin is None or keyword.origin == origin)
        and (source is None or source in (score.sources or []))
    ]
    selected.sort(key=lambda row: (-row[0].score, row[1].id))
    selected = selected[:limit]
    seeds = _seed_texts(session)
    history = _sparklines(session, [k.id for _, k in selected], latest)
    return TrendPage(
        date=latest,
        items=[_trend_out(s, k, seeds, history.get(k.id, [])) for s, k in selected],
    )


@router.get("/trends/{keyword_id}", response_model=TrendDetail)
def trend_detail(keyword_id: int, session: Session = Depends(get_session)) -> TrendDetail:
    keyword = session.get(Keyword, keyword_id)
    if keyword is None:
        raise HTTPException(status_code=404, detail="Keyword not found")
    seeds = _seed_texts(session)
    latest_score = session.scalar(
        select(KeywordScore)
        .where(KeywordScore.keyword_id == keyword_id)
        .order_by(KeywordScore.date.desc())
        .limit(1)
    )
    trend = None
    if latest_score is not None:
        sparkline = _sparklines(session, [keyword_id], latest_score.date).get(keyword_id, [])
        trend = _trend_out(latest_score, keyword, seeds, sparkline)

    anchor = (
        latest_score.date
        if latest_score
        else session.scalar(
            select(func.max(TrendSignal.date)).where(TrendSignal.keyword_id == keyword_id)
        )
    )
    signals: list[SignalSeries] = []
    if anchor is not None:
        since = anchor - timedelta(days=HISTORY_DAYS - 1)
        grouped: dict[tuple[str, str], list[SignalPoint]] = defaultdict(list)
        for source, metric, day, value in session.execute(
            select(TrendSignal.source, TrendSignal.metric, TrendSignal.date, TrendSignal.value)
            .where(
                TrendSignal.keyword_id == keyword_id,
                TrendSignal.date >= since,
                TrendSignal.date <= anchor,
            )
            .order_by(TrendSignal.source, TrendSignal.metric, TrendSignal.date)
        ):
            grouped[(source, metric)].append(SignalPoint(date=day, value=value))
        signals = [SignalSeries(source=s, metric=m, points=p) for (s, m), p in grouped.items()]

    return TrendDetail(
        keyword_id=keyword.id,
        keyword=keyword.text,
        origin=keyword.origin,
        is_pod_relevant=keyword.is_pod_relevant,
        is_seed=keyword.text in seeds,
        trend=trend,
        signals=signals,
        related=_related(session, keyword_id),
    )


def _related(session: Session, keyword_id: int) -> list[RelatedKeywordOut]:
    pairs = [
        (rel.child_id, "child", rel.source)
        for rel in session.scalars(
            select(KeywordRelation).where(KeywordRelation.parent_id == keyword_id)
        )
    ] + [
        (rel.parent_id, "parent", rel.source)
        for rel in session.scalars(
            select(KeywordRelation).where(KeywordRelation.child_id == keyword_id)
        )
    ]
    out = []
    for other_id, relation, source in pairs:
        other = session.get(Keyword, other_id)
        score = session.scalar(
            select(KeywordScore.score)
            .where(KeywordScore.keyword_id == other_id)
            .order_by(KeywordScore.date.desc())
            .limit(1)
        )
        out.append(
            RelatedKeywordOut(
                keyword_id=other.id,
                keyword=other.text,
                relation=relation,
                source=source,
                score=score,
                is_pod_relevant=other.is_pod_relevant,
            )
        )
    out.sort(key=lambda r: (r.score is None, -(r.score or 0), r.keyword))
    return out
