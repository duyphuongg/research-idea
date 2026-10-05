from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analysis.scoring import HISTORY_DAYS, Series, Weights, load_weights, score_keywords
from app.models import KeywordScore, TrendSignal


def rescore(session: Session, today: date, weights: Weights | None = None) -> int:
    """Recompute keyword_scores for `today` from the last 30 days of signals.
    Does not commit.
    """
    since = today - timedelta(days=HISTORY_DAYS - 1)
    rows = session.execute(
        select(
            TrendSignal.keyword_id,
            TrendSignal.source,
            TrendSignal.metric,
            TrendSignal.date,
            TrendSignal.value,
        ).where(TrendSignal.date >= since, TrendSignal.date <= today)
    )
    signals: dict[int, dict[tuple[str, str], Series]] = defaultdict(
        lambda: defaultdict(list)
    )
    for keyword_id, source, metric, day, value in rows:
        signals[keyword_id][(source, metric)].append((day, value))

    results = score_keywords(signals, today, weights or load_weights())
    session.execute(delete(KeywordScore).where(KeywordScore.date == today))
    session.add_all(
        KeywordScore(
            keyword_id=r.keyword_id,
            date=today,
            score=r.score,
            demand=r.demand,
            momentum=r.momentum,
            competition=r.competition,
            growth=r.growth,
            sources_rising=r.sources_rising,
            sources=list(r.sources),
        )
        for r in results
    )
    session.flush()
    return len(results)
