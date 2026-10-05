from app.keywords import canonical_keyword, get_or_create_keyword


def test_discovered_singular_plural_share_one_keyword(session):
    a = get_or_create_keyword(session, "nurse gifts", "discovered", has_parent=True)
    b = get_or_create_keyword(session, "nurse gift", "discovered", has_parent=True)
    assert a.id == b.id
    assert a.text == "nurse gift"


def test_discovered_is_canonicalised_and_seed_is_not(session):
    assert get_or_create_keyword(session, "Christmas Shirts", "discovered", has_parent=True).text == "christmas shirt"
    assert get_or_create_keyword(session, "dog moms").text == "dog moms"
    assert canonical_keyword("  Dress  GIFTS ") == "dress gift"
