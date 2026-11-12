"""Progress checkpoints for Phase 33."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase33.constants import REPORTS_DIR

UTC = timezone.utc


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_progress(path: Path | None = None) -> dict[str, Any]:
    p = path or (REPORTS_DIR / "progress.json")
    if not p.is_file():
        return {
            "phase": 33,
            "completed_stages": [],
            "current_stage": None,
            "download_attempts": [],
            "download_results": [],
            "source_evidence": [],
            "errors": [],
            "remaining_stages": [],
            "updated_utc": None,
        }
    return json.loads(p.read_text(encoding="utf-8"))


def save_progress(data: dict[str, Any], path: Path | None = None) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    p = path or (REPORTS_DIR / "progress.json")
    data["updated_utc"] = _now()
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def mark_stage(
    stage: str,
    *,
    completed: bool = False,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prog = load_progress()
    prog["current_stage"] = stage
    if completed and stage not in prog["completed_stages"]:
        prog["completed_stages"].append(stage)
    if error:
        prog["errors"].append({"stage": stage, "error": error, "utc": _now()})
    if extra:
        prog.setdefault("notes", []).append({"stage": stage, "utc": _now(), **extra})
    save_progress(prog)
    return prog


def write_json(name: str, payload: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path
