import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.pod_filter import singularize
from app.analysis.us_calendar import Occurrence
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


def seed_ideas(session: Session, occ: Occurrence, scores: dict[int, float]) -> list[CalendarIdea]:
    if not occ.event.theme_words:
        return []
    lead = occ.event.theme_words[0]
    seed_texts = set(session.scalars(select(Seed.keyword)))
    ideas = []
    for seed in session.scalars(select(Seed).where(Seed.active.is_(True)).order_by(Seed.id)):
        text = normalize_keyword(f"{lead} {seed.keyword}")
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
