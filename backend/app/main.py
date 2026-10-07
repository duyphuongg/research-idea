import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from app.api import calendar as calendar_api
from app.api import signals as signals_api
from app.api import health, products, scans, seeds, trends
from app.api import settings as settings_api
from app.config import Settings, get_settings
from app.connectors.registry import ConnectorFactory, build_connectors
from app.db import make_engine, make_session_factory
from app.pipeline.jobs import JobFactory, build_jobs
from app.scheduler import start_scheduler
from app.services.scans import mark_interrupted_scans


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    connector_factory: ConnectorFactory = build_connectors,
    job_factory: JobFactory = build_jobs,
) -> FastAPI:
    settings = settings or get_settings()
    if session_factory is None:
        session_factory = make_session_factory(make_engine(settings.database_url))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with session_factory() as session:
            mark_interrupted_scans(session)
            session.commit()
        scheduler = start_scheduler(app) if settings.scheduler_enabled else None
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)

    app = FastAPI(title="POD Trend Radar", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.connector_factory = connector_factory
    app.state.job_factory = job_factory
    app.state.scan_lock = threading.Lock()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    for module in (products, seeds, settings_api, scans, health, trends, calendar_api, signals_api):
        app.include_router(module.router)
    return app
