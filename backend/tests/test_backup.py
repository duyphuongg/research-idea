import sqlite3
from datetime import date
from pathlib import Path

from app.services.backup import backup_database, sqlite_path


def _make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("create table t (x int)")
    con.execute("insert into t values (42)")
    con.commit()
    con.close()


def test_sqlite_path():
    assert sqlite_path("sqlite:///./data/radar.db", Path("/app")) == Path("/app/data/radar.db")
    assert sqlite_path("sqlite:////abs/radar.db", Path("/app")) == Path("/abs/radar.db")
    assert sqlite_path("sqlite://", Path("/app")) is None
    assert sqlite_path("postgresql://x/y", Path("/app")) is None


def test_backup_copies_data_and_overwrites_same_day(tmp_path):
    db = tmp_path / "radar.db"
    _make_db(db)
    out = backup_database(db, tmp_path / "backups", keep=14, today=date(2026, 10, 8))
    assert out.name == "radar-2026-10-08.db"
    assert sqlite3.connect(out).execute("select x from t").fetchone() == (42,)
    con = sqlite3.connect(db)
    con.execute("insert into t values (7)")
    con.commit()
    con.close()
    backup_database(db, tmp_path / "backups", keep=14, today=date(2026, 10, 8))
    assert sqlite3.connect(out).execute("select count(*) from t").fetchone() == (2,)
    assert [p.name for p in (tmp_path / "backups").iterdir()] == ["radar-2026-10-08.db"]


def test_backup_keeps_only_latest_n(tmp_path):
    db = tmp_path / "radar.db"
    _make_db(db)
    dest = tmp_path / "backups"
    for day in range(1, 6):
        backup_database(db, dest, keep=3, today=date(2026, 10, day))
    assert sorted(p.name for p in dest.iterdir()) == [
        "radar-2026-10-03.db", "radar-2026-10-04.db", "radar-2026-10-05.db",
    ]
