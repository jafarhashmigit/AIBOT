"""Phase 34 progress + JSON helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase34.constants import REPORTS_DIR

UTC = timezone.utc


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(name: str, payload: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path


def load_progress() -> dict[str, Any]:
    p = REPORTS_DIR / "progress.json"
    if not p.is_file():
        return {
            "phase": 34,
            "completed_stages": [],
            "current_stage": None,
            "errors": [],
            "updated_utc": None,
        }
    return json.loads(p.read_text(encoding="utf-8"))


def save_progress(data: dict[str, Any]) -> Path:
    data["updated_utc"] = _now()
    return write_json("progress.json", data)


def mark_stage(stage: str, *, completed: bool = False, extra: dict[str, Any] | None = None) -> None:
    prog = load_progress()
    prog["current_stage"] = stage
    if completed and stage not in prog["completed_stages"]:
        prog["completed_stages"].append(stage)
    if extra:
        prog.setdefault("notes", []).append({"stage": stage, "utc": _now(), **extra})
    save_progress(prog)
