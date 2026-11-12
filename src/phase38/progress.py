from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase38.constants import REPORTS_DIR

UTC = timezone.utc


def write_json(name: str, payload: Any) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
