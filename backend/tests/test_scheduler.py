from types import SimpleNamespace

from app.scheduler import JOB_ID, reschedule, start_scheduler
from app.settings_store import set_setting


async def test_scheduler_uses_stored_hour_and_reschedules(session_factory):
    with session_factory() as s:
        set_setting(s, "scan_hour_utc", 5)
        s.commit()
    app = SimpleNamespace(state=SimpleNamespace(session_factory=session_factory))

    scheduler = start_scheduler(app)
    try:
        assert app.state.scheduler is scheduler
        assert scheduler.get_job(JOB_ID).next_run_time.hour == 5
        reschedule(app, 3)
        assert scheduler.get_job(JOB_ID).next_run_time.hour == 3
    finally:
        scheduler.shutdown(wait=False)


def test_reschedule_without_scheduler_is_noop():
    reschedule(SimpleNamespace(state=SimpleNamespace()), 3)
