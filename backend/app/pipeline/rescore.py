from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analysis.scoring import HISTORY_DAYS, Series, Weights, load_weights, score_keywords
from app.analysis.pod_filter import (
    PodFilterRules,
    adds_only_product_words,
    is_pod_relevant,
    load_rules,
)
from app.keywords import canonical_keyword
from app.models import (
    Keyword,
    KeywordRelation,
    KeywordScore,
    ProductKeyword,
    Seed,
    TrendSignal,
)


def refilter(session: Session, rules: PodFilterRules | None = None) -> int:
    """Re-evaluate is_pod_relevant for all keywords against current rules. Does not commit."""
    rules = rules or load_rules()
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


def merge_duplicate_keywords(session: Session) -> int:
    """Merge/rename discovered keywords whose text is not canonical. Does not commit."""
    seed_texts = set(session.scalars(select(Seed.keyword)))
    count = 0
    candidates = [
        k
        for k in session.scalars(select(Keyword).where(Keyword.origin == "discovered"))
        if canonical_keyword(k.text) != k.text and k.text not in seed_texts
    ]
    for dup in candidates:
        canon = canonical_keyword(dup.text)
        target = session.scalar(select(Keyword).where(Keyword.text == canon))
        if target is None:
            dup.text = canon
            session.flush()
            count += 1
            continue
        _merge_into(session, dup, target)
        count += 1
    session.flush()
    return count


def _merge_into(session: Session, dup: Keyword, target: Keyword) -> None:
    did, tid = dup.id, target.id
    # trend signals
    existing = {
        (s.source, s.metric, s.date): s
        for s in session.scalars(select(TrendSignal).where(TrendSignal.keyword_id == tid))
    }
    for s in session.scalars(select(TrendSignal).where(TrendSignal.keyword_id == did)).all():
        key = (s.source, s.metric, s.date)
        if key in existing:
            existing[key].value = max(existing[key].value, s.value)
            session.delete(s)
        else:
            s.keyword_id = tid
            existing[key] = s
    session.flush()
    # relations
    rels = {
        (r.parent_id, r.child_id, r.source): r
        for r in session.scalars(select(KeywordRelation))
    }
    for r in list(rels.values()):
        if did not in (r.parent_id, r.child_id):
            continue
        parent = tid if r.parent_id == did else r.parent_id
        child = tid if r.child_id == did else r.child_id
        del rels[(r.parent_id, r.child_id, r.source)]
        key = (parent, child, r.source)
        if parent == child:
            session.delete(r)
        elif key in rels:
            rels[key].last_seen = max(rels[key].last_seen, r.last_seen)
            session.delete(r)
        else:
            session.delete(r)
            session.flush()
            new = KeywordRelation(
                parent_id=parent, child_id=child, source=r.source, last_seen=r.last_seen
            )
            session.add(new)
            rels[key] = new
    session.flush()
    # product keywords
    pks = {
        pk.product_id: pk
        for pk in session.scalars(select(ProductKeyword).where(ProductKeyword.keyword_id == tid))
    }
    for pk in session.scalars(select(ProductKeyword).where(ProductKeyword.keyword_id == did)).all():
        cur = pks.get(pk.product_id)
        if cur is not None:
            cur.rank = min(cur.rank, pk.rank)
            cur.last_seen = max(cur.last_seen, pk.last_seen)
            session.delete(pk)
        else:
            session.delete(pk)
            session.flush()
            pks[pk.product_id] = ProductKeyword(
                product_id=pk.product_id, keyword_id=tid, rank=pk.rank, last_seen=pk.last_seen
            )
            session.add(pks[pk.product_id])
    session.flush()
    session.execute(delete(KeywordScore).where(KeywordScore.keyword_id == did))
    target.first_seen_at = min(target.first_seen_at, dup.first_seen_at)
    session.expire(dup)
    session.delete(dup)
    session.flush()


def rescore(session: Session, today: date, weights: Weights | None = None) -> int:
    """Recompute keyword_scores for `today` from the last 30 days of signals.
    Does not commit.
    """
    merge_duplicate_keywords(session)
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
