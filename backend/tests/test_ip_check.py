from app.analysis.ip_check import IpIndex, TeamRef
from app.analysis.nfl_match import PlayerIndex, PlayerRef


def _index():
    return IpIndex(
        terms={"red": {"league": ["NFL", "Super Bowl"], "brand": ["Comfort Colors"], "celebrity": ["Taylor Swift"]},
               "yellow": {"slogan": ["Who Dey", "dog mom"]}},
        generic_nicknames=["cowboys", "eagles"],
        teams=[TeamRef("Dallas Cowboys", "Cowboys"), TeamRef("New York Yankees", "Yankees"),
               TeamRef("Philadelphia Eagles", "Eagles")],
        players=["Jayden Daniels", "Marvin Harrison Jr.", "CeeDee Lamb"],
        player_matcher=PlayerIndex([PlayerRef("1", "CeeDee", "Lamb", "DAL")]),
    )


def test_levels_and_hits():
    idx = _index()
    assert idx.check("hockey mom shirt") == {"level": "green", "hits": []}
    r = idx.check("Funny NFL football mom")
    assert r["level"] == "red" and r["hits"] == [{"term": "nfl", "category": "league", "level": "red"}]
    assert idx.check("super bowls party")["level"] == "red"  # plural
    assert idx.check("comfort colors tee")["hits"][0]["category"] == "brand"
    assert idx.check("who dey shirt")["level"] == "yellow"


def test_teams_and_players():
    idx = _index()
    assert idx.check("Dallas Cowboys fan")["hits"] == [{"term": "dallas cowboys", "category": "team", "level": "red"}]
    assert idx.check("cowboys and cowgirls")["level"] == "green"  # generic nickname alone
    assert idx.check("yankees mom")["hits"] == [{"term": "yankees", "category": "team_nickname", "level": "yellow"}]
    assert idx.check("jayden daniels injury")["hits"][0] == {"term": "jayden daniels", "category": "player", "level": "red"}
    assert idx.check("marvin harrison jr")["level"] == "red"


def test_worst_level_wins_and_no_duplicates():
    r = _index().check("Taylor Swift NFL dog mom NFL")
    assert r["level"] == "red"
    assert [h["term"] for h in r["hits"]] == ["taylor swift", "nfl", "dog mom"]


def test_player_short_form():
    r = _index().check("cd lamb shirt")
    assert r["level"] == "red" and r["hits"] == [{"term": "ceedee lamb", "category": "player", "level": "red"}]
