"""IP-risk index built from config/ip_terms.yaml, ESPN team names and NFL rosters (cached in-process)."""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.ip_check import IpIndex, TeamRef
from app.analysis.nfl_match import PlayerIndex, PlayerRef
from app.config_files import load_yaml
from app.models import NflPlayer, SportsTeam

USPTO_URL = "https://tmsearch.uspto.gov/search/search-information"
CACHE_SECONDS = 600
_cache: dict[str, tuple[float, IpIndex]] = {}


def build_index(session: Session) -> IpIndex:
    data = load_yaml("ip_terms.yaml")
    return IpIndex(
        terms={"red": data.get("red") or {}, "yellow": data.get("yellow") or {}},
        generic_nicknames=data.get("generic_nicknames") or [],
        teams=[TeamRef(t.full_name, t.nickname) for t in session.scalars(select(SportsTeam))],
        players=list(session.scalars(select(NflPlayer.name))),
        player_matcher=PlayerIndex(
            PlayerRef(p.athlete_id, p.first_name, p.last_name, p.team) for p in session.scalars(select(NflPlayer))
        ),
    )


def ip_index(session: Session) -> IpIndex:
    """Shared index, rebuilt at most every CACHE_SECONDS (the hourly job refreshes teams/rosters)."""
    key = str(session.get_bind().url)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    index = build_index(session)
    _cache[key] = (time.monotonic(), index)
    return index


def clear_cache() -> None:
    _cache.clear()
