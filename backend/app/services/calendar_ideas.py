import re
from itertools import groupby

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.pod_filter import singularize
from app.analysis.us_calendar import EventDef, Occurrence, load_calendar
from app.api.schemas import CalendarIdea, CalendarMatch
from app.keywords import canonical_keyword, normalize_keyword
from app.models import Keyword, KeywordScore, Seed


def _tokens(text: str) -> set[str]:
    return {singularize(t) for t in re.findall(r"[a-z0-9]+", text.lower())}


def latest_scores(session: Session) -> dict[int, float]:
    latest = session.scalar(select(func.max(KeywordScore.date)))
    if latest is None:
        return {}
    rows = session.execute(
        select(KeywordScore.keyword_id, KeywordScore.score).where(KeywordScore.date == latest)
    )
    return {keyword_id: score for keyword_id, score in rows}


def seed_ideas(
    session: Session,
    occ: Occurrence,
    scores: dict[int, float],
    all_events: list[EventDef] | None = None,
) -> list[CalendarIdea]:
    event = occ.event
    if not event.theme_words or not event.cross_seeds:
        return []
    lead = event.theme_words[0]
    if all_events is None:
        all_events = load_calendar().events
    # Seeds sharing a word with any event's lead or this template's literal words
    # would produce nonsense ("halloween halloween nurse", "nurse gift gift").
    # Events with cross_seeds off never prefix seeds, so their leads don't count.
    blocked = _tokens(event.idea_template.replace("{lead}", " ").replace("{seed}", " "))
    for e in all_events:
        if e.theme_words and e.cross_seeds:
            blocked |= _tokens(e.theme_words[0])
    active = list(session.scalars(select(Seed).where(Seed.active.is_(True)).order_by(Seed.id)))
    seed_texts = {normalize_keyword(s.keyword) for s in active}
    ideas = []
    seen: set[str] = set()
    for seed in active:
        if _tokens(seed.keyword) & blocked:
            continue
        raw = event.idea_template.format(lead=lead, seed=seed.keyword)
        text = normalize_keyword(" ".join(t for t, _ in groupby(raw.split())))
        if text in seen:
            continue
        seen.add(text)
        keyword = session.scalar(select(Keyword).where(Keyword.text == text)) or session.scalar(
            select(Keyword).where(Keyword.text == canonical_keyword(text))
        )
        ideas.append(
            CalendarIdea(
                keyword=text,
                keyword_id=keyword.id if keyword else None,
                score=scores.get(keyword.id) if keyword else None,
                is_seed=text in seed_texts,
            )
        )
    return ideas


def radar_matches(
    session: Session, occ: Occurrence, scores: dict[int, float], limit: int = 8
) -> list[CalendarMatch]:
    themes = [_tokens(w) for w in occ.event.theme_words if w]
    if not themes or not scores:
        return []
    keywords = session.scalars(
        select(Keyword).where(Keyword.id.in_(scores.keys()), Keyword.is_pod_relevant.is_(True))
    )
    matches = [
        CalendarMatch(keyword_id=k.id, keyword=k.text, score=scores[k.id])
        for k in keywords
        if any(theme <= _tokens(k.text) for theme in themes)
    ]
    matches.sort(key=lambda m: (-m.score, m.keyword))
    return matches[:limit]
