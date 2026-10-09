"""Recognise NFL players/teams in a trending search (and its news titles)."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.analysis.pod_filter import singularize

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
TEAMS = {
    "cardinals": "ARI", "falcons": "ATL", "ravens": "BAL", "bills": "BUF", "panthers": "CAR", "bears": "CHI",
    "bengals": "CIN", "browns": "CLE", "cowboys": "DAL", "broncos": "DEN", "lions": "DET", "packers": "GB",
    "texans": "HOU", "colts": "IND", "jaguars": "JAX", "chiefs": "KC", "raiders": "LV", "chargers": "LAC",
    "rams": "LAR", "dolphins": "MIA", "vikings": "MIN", "patriots": "NE", "saints": "NO", "giants": "NYG",
    "jets": "NYJ", "eagles": "PHI", "steelers": "PIT", "49ers": "SF", "seahawks": "SEA", "buccaneers": "TB",
    "titans": "TEN", "commanders": "WSH",
}
FOOTBALL_WORDS = re.compile(
    r"\b(nfl|football|quarterback|qb|touchdowns?|tds?|wide receiver|running back|linebacker|cornerback|"
    r"head coach|super bowl|sunday night|monday night|thursday night)\b"
)
NFL_WORD = re.compile(r"\bnfl\b")


@dataclass(frozen=True)
class PlayerRef:
    athlete_id: str
    first_name: str
    last_name: str
    team: str | None


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower().replace("'", ""))
    return [singularize(w) for w in words if w not in SUFFIXES]


class PlayerIndex:
    def __init__(self, players: Iterable[PlayerRef]):
        self._by_last: dict[str, list[tuple[list[str], PlayerRef]]] = {}
        for p in players:
            last, first = tokens(p.last_name), tokens(p.first_name)
            if last and first:
                self._by_last.setdefault(last[-1], []).append((first + last[:-1], p))

    def find(self, words: Sequence[str]) -> PlayerRef | None:
        exact: dict[str, PlayerRef] = {}
        loose: dict[str, PlayerRef] = {}
        for i in range(1, len(words)):
            for first, p in self._by_last.get(words[i], []):
                before = words[i - 1]
                if before == first[-1] or (len(first) == 1 and before == first[0]):
                    exact[p.athlete_id] = p
                elif before[0] == first[0][0] and len(before) <= 3:  # "cd lamb", "aj brown"
                    loose[p.athlete_id] = p
        pool = exact or loose
        return next(iter(pool.values())) if len(pool) == 1 else None


def match_moment(
    query: str, news_titles: Sequence[str], players: Iterable[PlayerRef] | PlayerIndex
) -> tuple[str | None, str | None] | None:
    """(athlete_id, team) for an NFL-related trend; None when it is not about the NFL."""
    index = players if isinstance(players, PlayerIndex) else PlayerIndex(players)
    player = index.find(tokens(query))
    if player is not None:
        return player.athlete_id, player.team
    news = " ".join(news_titles).lower()
    football = bool(FOOTBALL_WORDS.search(news))
    if football:
        for word in re.findall(r"[a-z0-9]+", query.lower()):
            if word in TEAMS:
                return None, TEAMS[word]
        for word in re.findall(r"[a-z0-9]+", news):  # e.g. a player we could not pin down
            if word in TEAMS and NFL_WORD.search(news):
                return None, TEAMS[word]
    if NFL_WORD.search(news) or NFL_WORD.search(query.lower()):
        return None, None
    return None
