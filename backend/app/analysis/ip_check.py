"""Local IP-risk check: league/brand/character/celebrity terms, team names and NFL player names."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.analysis.nfl_match import PlayerIndex, tokens

MAX_NGRAM = 5
RANK = {"green": 0, "yellow": 1, "red": 2}


@dataclass(frozen=True)
class TeamRef:
    full_name: str  # "Dallas Cowboys"
    nickname: str  # "Cowboys"


class IpIndex:
    def __init__(
        self,
        terms: dict[str, dict[str, list[str]]],
        generic_nicknames: Iterable[str],
        teams: Iterable[TeamRef],
        players: Iterable[str],
        player_matcher: PlayerIndex | None = None,
    ) -> None:
        self._matcher = player_matcher  # also catches short forms such as "cd lamb"
        self._index: dict[tuple[str, ...], tuple[str, str, str]] = {}  # tokens -> (term, category, level)
        generic = {tuple(tokens(n)) for n in generic_nicknames}
        for level in ("yellow", "red"):  # red added last wins over yellow on equal tokens
            for category, words in (terms.get(level) or {}).items():
                for word in words or []:
                    self._add(str(word), category, level)
        for team in teams:
            self._add(team.full_name, "team", "red")
            key = tuple(tokens(team.nickname))
            if key and key not in generic and key not in self._index:
                self._add(team.nickname, "team_nickname", "yellow")
        for name in players:
            self._add(name, "player", "red")

    def _add(self, text: str, category: str, level: str) -> None:
        key = tuple(tokens(text))
        if 0 < len(key) <= MAX_NGRAM:
            current = self._index.get(key)
            if current is None or RANK[level] >= RANK[current[2]]:
                self._index[key] = (_plain(text), category, level)

    def check(self, text: str) -> dict:
        words = tokens(text)
        hits: list[dict] = []
        seen: set[str] = set()
        i = 0
        while i < len(words):
            for n in range(min(MAX_NGRAM, len(words) - i), 0, -1):  # longest match first
                found = self._index.get(tuple(words[i:i + n]))
                if found:
                    term, category, level = found
                    if term not in seen:
                        seen.add(term)
                        hits.append({"term": term, "category": category, "level": level})
                    i += n
                    break
            else:
                i += 1
        if self._matcher is not None and not any(h["category"] == "player" for h in hits):
            player = self._matcher.find(words)
            if player is not None:
                hits.append({"term": _plain(f"{player.first_name} {player.last_name}"), "category": "player",
                             "level": "red"})
        level = max((h["level"] for h in hits), key=RANK.__getitem__, default="green")
        return {"level": level, "hits": hits}


def _plain(name: str) -> str:
    """Display form: lowercase words without punctuation or name suffixes ("marvin harrison")."""
    return " ".join(w for w in re.findall(r"[a-z0-9]+", name.lower().replace("'", ""))
                    if w not in {"jr", "sr", "ii", "iii", "iv", "v"})
