import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base, make_session_factory
from app.main import create_app
import app.models  # noqa: F401  (registers tables on Base.metadata)


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return make_session_factory(engine)


@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture
def settings():
    return Settings(
        database_url="sqlite://",
        etsy_api_key="test-key",
        scheduler_enabled=False,
        _env_file=None,
    )


@pytest.fixture
def make_client(settings, session_factory):
    clients = []

    def _make(**kwargs):
        kwargs.setdefault("job_factory", lambda settings, overrides, only: [])
        c = TestClient(create_app(settings=settings, session_factory=session_factory, **kwargs))
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()


@pytest.fixture(autouse=True)
def _no_real_telegram(monkeypatch):
    """run_scan falls back to get_settings(), which reads backend/.env; never let tests reach Telegram."""
    import app.pipeline.scan as scan_mod

    monkeypatch.setattr(scan_mod, "get_settings", lambda: Settings(_env_file=None, scheduler_enabled=False))
