from app.analysis.amazon import (
    AmazonConfig,
    is_licensed,
    list_url,
    load_amazon_config,
    parse_rating,
    parse_reviews,
    title_phrases,
)

TERMS = ("superman", "spider-man", "ac/dc", "star wars", "nfl")


def test_load_config():
    cfg = load_amazon_config()
    assert isinstance(cfg, AmazonConfig)
    assert len(cfg.categories) == 8
    first = cfg.categories[0]
    assert (first.key, first.node, first.product_type) == ("women_tshirts", "9056923011", "tshirt")
    assert cfg.lists == ("bestsellers", "new_releases")
    assert cfg.pages == 2
    assert cfg.delay_seconds == (4.0, 8.0)
    assert cfg.min_phrase_products == 3 and cfg.max_phrases == 40
    assert "disney" in cfg.licensed_terms


def test_list_url():
    assert list_url("bestsellers", "123", 2) == "https://www.amazon.com/gp/bestsellers/fashion/123?pg=2"
    assert list_url("new_releases", "123", 1) == "https://www.amazon.com/gp/new-releases/fashion/123?pg=1"


def test_is_licensed():
    assert is_licensed("Popfunk Superman Classic Logo T-Shirt", TERMS)
    assert not is_licensed("Retro Superb Mom Shirt", TERMS)
    assert is_licensed("Marvel STAR WARS Tee", TERMS)
    assert is_licensed("Amazing Spider-Man Shirt", TERMS)
    assert is_licensed("Vintage AC/DC Tour Shirt", TERMS)
    assert not is_licensed("Unflagged Shirt", TERMS)
    assert not is_licensed("Superman", ())


def test_parse_reviews():
    assert parse_reviews(" 2,959") == 2959
    assert parse_reviews("1.2K") == 1200
    assert parse_reviews("(15)") == 15
    assert parse_reviews("2M") == 2_000_000
    assert parse_reviews("junk") is None
    assert parse_reviews("") is None
    assert parse_reviews(None) is None


def test_parse_rating():
    assert parse_rating("4.6 out of 5 stars") == 4.6
    assert parse_rating("5.0 out of 5 stars") == 5.0
    assert parse_rating("no stars") is None
    assert parse_rating(None) is None


TITLES = [
    "Funny Pickleball Shirt Gift",
    "Pickleball Mom Funny Pickleball T-Shirt",
    "I Love Pickleball Funny Pickleball Tee",
    "Spooky Season Ghost Shirt",
]


def test_title_phrases():
    out = title_phrases(TITLES, min_products=3, max_phrases=40)
    assert ("funny pickleball", 3) in out
    phrases = [p for p, _ in out]
    assert "pickleball" not in phrases
    assert all(len(p.split()) >= 2 for p in phrases)
    assert "shirt gift" not in phrases
    assert "t shirt" not in phrases
    assert not any(p.startswith("i ") for p in phrases)


def test_title_phrases_prefers_longer_and_drops_contained():
    titles = ["Dog Mama Club Tee", "Dog Mama Club Hoodie", "Dog Mama Club"]
    out = dict(title_phrases(titles, 3, 40))
    assert out == {"dog mama club": 3}


def test_title_phrases_keeps_shorter_with_higher_count():
    titles = ["Dog Mama Club", "Dog Mama Club", "Dog Mama Club", "Dog Mama Rocks"]
    out = dict(title_phrases(titles, 3, 40))
    assert out["dog mama"] == 4 and out["dog mama club"] == 3


def test_title_phrases_counts_once_per_product_and_caps():
    out = title_phrases(["Cat Cat Cat Dad Cat Dad"] * 3, 3, 1)
    assert len(out) == 1
    assert out[0][1] == 3


def test_title_phrases_real_titles():
    titles = [
        "Halloween Shirts Women Ghost Shirt Spooky Season Tee Fall Tops | "
        "I Found This Humerus Ghost Shirt Nurse Spooky Season Tees",
        "in October We Wear Pink Black Women Breast Cancer Awareness T-Shirt",
    ] * 3
    phrases = [p for p, _ in title_phrases(titles, 3, 40)]
    assert "spooky season" in phrases
    assert "breast cancer awareness" in phrases
    bad = {"top", "tee", "shirt", "tshirt", "t", "sweatshirt", "hoodie", "gift", "women", "in", "i", "this"}
    for p in phrases:
        w = p.split()
        assert w[0] not in bad and w[-1] not in bad
    assert "tops i found" not in phrases
    assert not any("tops i" in p or "tees" in p.split() for p in phrases)


def test_title_phrases_apostrophes():
    out = dict(title_phrases(["Best Mom's Club"] * 3, 3, 40))
    assert "best moms club" in out


def test_is_licensed_normalised():
    assert is_licensed("Spider Man Dad Shirt", ("spider-man",))
    assert is_licensed("Spider-Man Shirt", ("spider man",))
    assert is_licensed("AC DC Shirt", ("ac/dc",))
    assert is_licensed("AC/DC Shirt", ("ac dc",))
    assert not is_licensed("Ford Truck Dad", ("legend of zelda",))


def test_parse_edge_cases():
    assert parse_reviews("4.6") is None
    assert parse_reviews("-5") is None
    assert parse_reviews("1,234 ratings") is None
    assert parse_rating("10 out of 5") is None
