from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase44.constants import REPORTS_DIR


def write_json(name: str, payload: Any) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path
