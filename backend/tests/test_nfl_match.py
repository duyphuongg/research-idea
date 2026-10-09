from app.analysis.nfl_match import PlayerRef, match_moment, tokens


PLAYERS = [
    PlayerRef("1", "CeeDee", "Lamb", "DAL"),
    PlayerRef("2", "Jayden", "Daniels", "WSH"),
    PlayerRef("3", "Marvin", "Harrison Jr.", "ARI"),
    PlayerRef("4", "Daron", "Bland", "DAL"),
    PlayerRef("5", "Josh", "Allen", "BUF"),
    PlayerRef("6", "Josh", "Allen", "JAX"),  # two Josh Allens
    PlayerRef("7", "Cooper", "Kupp", "SEA"),
]


def test_tokens_normalize():
    assert tokens("Marvin Harrison Jr.") == ["marvin", "harrison"]
    assert tokens("Jayden Daniels' injury!") == ["jayden", "daniel", "injury"]


def test_player_matches():
    assert match_moment("cd lamb", [], PLAYERS) == ("1", "DAL")
    assert match_moment("jayden daniel injury", [], PLAYERS) == ("2", "WSH")
    assert match_moment("Jayden Daniels injury update", [], PLAYERS) == ("2", "WSH")
    assert match_moment("marvin harrison jr", [], PLAYERS) == ("3", "ARI")
    assert match_moment("daron bland", [], PLAYERS) == ("4", "DAL")
    assert match_moment("cooper", [], PLAYERS) is None
    assert match_moment("lamb recipe", [], PLAYERS) is None


def test_ambiguous_player_falls_back_to_team_or_none():
    assert match_moment("josh allen", [], PLAYERS) is None
    assert match_moment("josh allen", ["Josh Allen throws 3 TDs as Bills beat NFL rival"], PLAYERS) is not None


def test_team_needs_football_news():
    assert match_moment("cowboys vs eagles", ["Cowboys fall to Eagles in NFL thriller"], PLAYERS) == (None, "DAL")
    assert match_moment("giants", ["Giants win NLCS game 3"], PLAYERS) is None
    assert match_moment("49ers", ["49ers quarterback injured"], PLAYERS) == (None, "SF")


def test_generic_nfl_news():
    assert match_moment("roughing the passer", ["NFL refs under fire for roughing call"], PLAYERS) == (None, None)
    assert match_moment("georgia-alabama game", ["College football rankings"], PLAYERS) is None
