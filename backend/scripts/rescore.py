"""Recompute today's keyword scores from stored signals. Usage: python scripts/rescore.py"""

from datetime import datetime, timezone

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.pipeline.rescore import rescore


def main() -> None:
    today = datetime.now(timezone.utc).date()
    session_factory = make_session_factory(make_engine(get_settings().database_url))
    with session_factory() as session:
        count = rescore(session, today)
        session.commit()
    print(f"Rescored {count} keywords for {today}")


if __name__ == "__main__":
    main()
