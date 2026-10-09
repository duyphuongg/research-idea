from datetime import date

from app.models import Keyword, ListingSignal, Product, ProductKeyword, WorkItem
from app.services.work import blocked_subjects


def _kw(session, text="hockey mom"):
    k = Keyword(text=text, origin="seed")
    session.add(k)
    session.commit()
    return k


def _product(session, title="Hockey Mom Shirt", ext="1"):
    p = Product(source="etsy", external_id=ext, title=title, url=f"https://etsy.com/listing/{ext}",
                image_url="https://img/1.jpg", product_type="tshirt")
    session.add(p)
    session.commit()
    return p


def test_put_list_delete_keyword(client, session):
    k = _kw(session)
    r = client.put(f"/api/work/keyword/{k.id}", json={"status": "idea", "note": "  màu hồng  "})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "idea" and body["note"] == "màu hồng"
    assert body["title"] == "hockey mom" and body["link"] == "/niche?keyword=hockey+mom"

    client.put(f"/api/work/keyword/{k.id}", json={"status": "designing", "note": None})
    items = client.get("/api/work").json()
    assert len(items) == 1 and items[0]["status"] == "designing" and items[0]["note"] is None
    assert client.get("/api/work?status=idea").json() == []

    assert client.delete(f"/api/work/keyword/{k.id}").status_code == 204
    assert client.get("/api/work").json() == []
    assert client.delete(f"/api/work/keyword/{k.id}").status_code == 204


def test_product_item_links_to_its_keyword(client, session):
    k = _kw(session)
    p = _product(session)
    session.add(ProductKeyword(product_id=p.id, keyword_id=k.id, rank=1, last_seen=date(2026, 10, 9)))
    session.commit()
    body = client.put(f"/api/work/product/{p.id}", json={"status": "listed"}).json()
    assert body["title"] == "Hockey Mom Shirt" and body["image_url"] == "https://img/1.jpg"
    assert body["external_url"] == "https://etsy.com/listing/1"
    assert body["link"] == "/niche?keyword=hockey+mom"


def test_signal_product_links_via_discovery_query(client, session):
    p = _product(session, ext="2")
    session.add(ListingSignal(product_id=p.id, discovered_on=date(2026, 10, 9),
                              discovery_query="pickleball shirt", status="steady_grower"))
    session.commit()
    body = client.put(f"/api/work/product/{p.id}", json={"status": "idea"}).json()
    assert body["link"] == "/niche?keyword=pickleball"


def test_validation(client, session):
    k = _kw(session)
    assert client.put("/api/work/keyword/999", json={"status": "idea"}).status_code == 404
    assert client.put(f"/api/work/keyword/{k.id}", json={"status": "done"}).status_code == 422
    assert client.put(f"/api/work/shop/{k.id}", json={"status": "idea"}).status_code == 422
    assert client.put(f"/api/work/keyword/{k.id}", json={"status": "idea", "note": "x" * 501}).status_code == 422


def test_blocked_subjects(session):
    session.add_all([
        WorkItem(subject_kind="keyword", subject_id=1, status="listed"),
        WorkItem(subject_kind="keyword", subject_id=2, status="idea"),
        WorkItem(subject_kind="product", subject_id=3, status="skipped"),
    ])
    session.commit()
    assert blocked_subjects(session) == {("keyword", 1), ("product", 3)}
