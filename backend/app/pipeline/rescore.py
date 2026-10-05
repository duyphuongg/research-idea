from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analysis.scoring import HISTORY_DAYS, Series, Weights, load_weights, score_keywords
from app.analysis.pod_filter import PodFilterRules, adds_only_product_words, is_pod_relevant
from app.keywords import canonical_keyword
from app.models import Keyword, KeywordRelation, KeywordScore, Seed, TrendSignal


def refilter(session: Session, rules: PodFilterRules | None = None) -> int:
    """Re-evaluate is_pod_relevant for all keywords against current rules. Does not commit."""
    seed_texts = {t for kw in session.scalars(select(Seed.keyword)) for t in (kw, canonical_keyword(kw))}
    parents: dict[int, list[str]] = defaultdict(list)
    for child_id, parent_text in session.execute(
        select(KeywordRelation.child_id, Keyword.text).join(
            Keyword, Keyword.id == KeywordRelation.parent_id
        )
    ):
        parents[child_id].append(parent_text)
    changed = 0
    for k in session.scalars(select(Keyword)):
        if k.text in seed_texts:
            new = True
        elif k.origin == "seed":
            continue
        else:
            kp = parents.get(k.id, [])
            new = is_pod_relevant(
                k.text, origin=k.origin, has_parent=bool(kp), rules=rules
            ) and not any(adds_only_product_words(k.text, p) for p in kp)
        if k.is_pod_relevant != new:
            k.is_pod_relevant = new
            changed += 1
    session.flush()
    return changed


def rescore(session: Session, today: date, weights: Weights | None = None) -> int:
    """Recompute keyword_scores for `today` from the last 30 days of signals.
    Does not commit.
    """
    refilter(session)
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
