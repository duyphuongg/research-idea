import logging
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def load_yaml(name: str) -> dict[str, Any]:
    """Read backend/config/<name>; missing or empty file → {}.

    Cached per file and re-read whenever the file's mtime changes, so edits apply
    without restarting the backend.
    """
    path = CONFIG_DIR / name
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        logger.warning("config file %s not found, using defaults", path)
        _cache.pop(name, None)
        return {}
    cached = _cache.get(name)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _cache[name] = (mtime, data)
    return data
