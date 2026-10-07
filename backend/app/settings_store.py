import copy
from typing import Any

from sqlalchemy.orm import Session

from app.models import Setting

DEFAULTS: dict[str, Any] = {
    "scan_hour_utc": 11,  # 11:00 UTC = 7:00 ET = 18:00 giờ Việt Nam
    "connectors_enabled": {},  # name -> bool; missing means enabled
    "digest_last_week": None,  # ISO week ("2026-W41") of the last weekly Telegram digest sent
}


def get_setting(session: Session, key: str) -> Any:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = session.get(Setting, key)
    return copy.deepcopy(row.value if row is not None else DEFAULTS[key])


def set_setting(session: Session, key: str, value: Any) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
    session.flush()
