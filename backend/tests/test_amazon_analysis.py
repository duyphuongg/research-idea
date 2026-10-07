from app.analysis.amazon import (
    AmazonConfig,
    is_licensed,
    is_non_pod,
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
    assert any("spooky season" in p for p in phrases)
    assert "breast cancer awareness" in phrases
    bad = {"top", "tee", "shirt", "tshirt", "t", "sweatshirt", "hoodie", "gift", "women", "in", "i", "this"}
    for p in phrases:
        w = p.split()
        assert w[0] not in bad and w[-1] not in bad
    assert "tops i found" not in phrases
    assert not any("tops i" in p or "tees" in p.split() for p in phrases)


def test_title_phrases_rejects_apparel_and_filler_anywhere():
    t1 = (
        "Halloween Shirts Women Ghost Shirt Spooky Season Tee Fall Tops | "
        "I Found This Humerus Ghost Shirt Nurse Spooky Season Tees"
    )
    t2 = "in October We Wear Pink Black Women Breast Cancer Awareness T-Shirt"
    assert dict(title_phrases([t1] * 3, 3, 40)) == {
        "spooky season": 3, "nurse spooky season": 3, "humerus ghost": 3,
    }
    # "wear pink black" is filler-free, so it is kept (absorbs "wear pink").
    assert dict(title_phrases([t2] * 3, 3, 40)) == {
        "breast cancer awareness": 3, "wear pink black": 3,
    }
    assert "salt of the earth" not in dict(title_phrases(["Salt of the Earth Club"] * 3, 3, 40))
    assert dict(title_phrases(["Salt and Pepper Club"] * 3, 3, 40))["salt and pepper"] == 3


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


def test_title_phrases_ignores_garment_descriptors():
    t = "Women Long Sleeve Crew Neck Graphic Pullover Spooky Season Ghost Sweatshirt"
    phrases = dict(title_phrases([t] * 3, 3, 40))
    assert any("spooky season" in p for p in phrases)
    banned = {"sleeve", "neck", "pullover", "graphic", "long", "crew"}
    assert not any(banned & set(p.split()) for p in phrases)
    # configurable extra ignore words
    extra = dict(title_phrases(["Spooky Season Ghost Vibes"] * 3, 3, 40, ignore_words=("ghost",)))
    assert "spooky season" in extra and not any("ghost" in p for p in extra)


def test_is_non_pod_and_config():
    cfg = load_amazon_config()
    assert is_non_pod("Modify by Amazon Custom T-Shirt", cfg.non_pod_terms)
    assert is_non_pod("Women Mesh Sheer Top", cfg.non_pod_terms)
    assert not is_non_pod("Meshach Funny Shirt", cfg.non_pod_terms)
    assert "sleeve" in cfg.phrase_ignore_words


def test_license_matching_strips_accents():
    from app.analysis.amazon import is_licensed

    assert is_licensed("Pokémon Pikachu Shirt", ("pokemon",))
    assert is_licensed("Pokemon Shirt", ("pokémon",))


def test_new_licensed_and_ignore_terms_in_config():
    from app.analysis.amazon import is_licensed, load_amazon_config, title_phrases

    cfg = load_amazon_config()
    for t in ("hocus pocus", "jack daniel's", "blink-182", "officially licensed", "chucky", "wednesday addams"):
        assert t in cfg.licensed_terms
    assert is_licensed("Hocus Pocus Sanderson Sisters Tee", cfg.licensed_terms)
    assert is_licensed("Jack Daniel's Logo", cfg.licensed_terms)
    for w in ("pouch", "pocket", "kangaroo", "print", "printed", "front", "back", "version", "letter",
              "3d", "costume", "cosplay", "set", "piece", "pcs", "matching"):
        assert w in cfg.phrase_ignore_words
    titles = ["Kangaroo Pouch Pocket Spooky Ghost"] * 3
    assert title_phrases(titles, 3, 10, cfg.phrase_ignore_words) == [("spooky ghost", 3)]
