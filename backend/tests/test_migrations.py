from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.db import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_migrations_create_every_model_table(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False

    command.upgrade(cfg, "head")

    tables = set(inspect(create_engine(url)).get_table_names())
    assert set(Base.metadata.tables) <= tables


def test_drop_amazon_alerts_migration_deletes_only_amazon_rows(tmp_path):
    url = f"sqlite:///{tmp_path / 'a.db'}"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "6ed06a8bb741")

    engine = create_engine(url)
    with engine.begin() as conn:
        for kind in ("amazon", "niche", "amazon", "listing"):
            conn.execute(text(
                "INSERT INTO alerts (kind, subject_id, level, priority, title, reason, link, scan_date, created_at)"
                " VALUES (:k, 1, 1, 0, 't', 'r', '/x', '2026-10-08', '2026-10-08 12:00:00')"
            ), {"k": kind})

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        kinds = sorted(conn.execute(text("SELECT kind FROM alerts")).scalars())
    assert kinds == ["listing", "niche"]


def test_products_shop_id_is_indexed(tmp_path):
    url = f"sqlite:///{tmp_path / 'i.db'}"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

    indexed = [i["column_names"] for i in inspect(create_engine(url)).get_indexes("products")]
    assert ["shop_id"] in indexed
    assert Base.metadata.tables["products"].c.shop_id.index is True
