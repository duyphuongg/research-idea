"""Daily copy of the SQLite database (one file per day, newest N kept)."""

import sqlite3
from datetime import date
from pathlib import Path

PREFIX = "radar-"


def sqlite_path(database_url: str, base_dir: Path) -> Path | None:
    """File path of a sqlite:/// URL (relative paths resolve against base_dir); None otherwise."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url == prefix:
        return None
    path = Path(database_url[len(prefix):])
    return path if path.is_absolute() else (base_dir / path).resolve()


def backup_database(db_path: Path, dest_dir: Path, *, keep: int = 14, today: date | None = None) -> Path:
    """Consistent online copy via SQLite's backup API; a second run on the same day replaces it."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{PREFIX}{(today or date.today()):%Y-%m-%d}.db"
    tmp = target.with_name(target.name + ".tmp")
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    tmp.replace(target)
    for old in sorted(dest_dir.glob(f"{PREFIX}*.db"))[:-keep]:
        old.unlink()
    return target
