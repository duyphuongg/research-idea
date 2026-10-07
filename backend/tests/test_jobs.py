from app.config import Settings
from app.pipeline.jobs import build_jobs


def _settings(key="k"):
    return Settings(etsy_api_key=key, _env_file=None)


def test_no_etsy_key_means_no_jobs():
    assert build_jobs(_settings(""), {}) == []


def test_override_disables_job():
    assert build_jobs(_settings(), {"etsy_signals": False}) == []


def test_only_other_source_excludes_job():
    assert build_jobs(_settings(), {}, ["etsy"]) == []


def test_only_etsy_signals_selects_job():
    assert [j.name for j in build_jobs(_settings(), {}, ["etsy_signals"])] == ["etsy_signals"]


def test_no_filter_returns_job():
    assert [j.name for j in build_jobs(_settings(), {}, None)] == ["etsy_signals"]
