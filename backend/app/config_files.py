from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


@lru_cache
def load_yaml(name: str) -> dict[str, Any]:
    """Read backend/config/<name>; missing or empty file → {}."""
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
