"""Checkpoint / progress helpers for long-running Phase 30 research."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase30.constants import REPORTS_DIR


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def progress_path(reports_dir: Path | None = None) -> Path:
    return (reports_dir or REPORTS_DIR) / "progress.json"


def load_progress(reports_dir: Path | None = None) -> dict[str, Any]:
    p = progress_path(reports_dir)
    if not p.exists():
        return {
            "stage": "init",
            "completed_strategies": [],
            "completed_folds": [],
            "completed_robustness": [],
            "last_successful_operation": None,
            "updated_at_utc": None,
        }
    return json.loads(p.read_text(encoding="utf-8"))


def save_progress(state: dict[str, Any], reports_dir: Path | None = None) -> Path:
    out = reports_dir or REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["updated_at_utc"] = _now()
    p = progress_path(out)
    p.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def log(msg: str) -> None:
    print(f"[PHASE30] {msg}", flush=True)
