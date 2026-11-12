"""Checkpoint / progress helpers for Phase 31."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase31.constants import REPORTS_DIR

STAGES = [
    "preflight",
    "data_integrity",
    "feature_audit",
    "label_reconstruction",
    "execution_cost_audit",
    "buy_sell_diagnostics",
    "horizon_analysis",
    "prediction_diagnostics",
    "statistical_audit",
    "cost_sensitivity",
    "root_cause",
    "final_verdict",
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def progress_path(reports_dir: Path | None = None) -> Path:
    return (reports_dir or REPORTS_DIR) / "progress.json"


def load_progress(reports_dir: Path | None = None) -> dict[str, Any]:
    p = progress_path(reports_dir)
    if not p.exists():
        return {
            "stage": "init",
            "completed_stages": [],
            "completed_audits": [],
            "completed_tests": False,
            "last_successful_operation": None,
            "errors": [],
            "remaining_stages": list(STAGES),
            "updated_at_utc": None,
        }
    return json.loads(p.read_text(encoding="utf-8"))


def save_progress(state: dict[str, Any], reports_dir: Path | None = None) -> Path:
    out = reports_dir or REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    done = set(state.get("completed_stages") or [])
    state["remaining_stages"] = [s for s in STAGES if s not in done]
    state["updated_at_utc"] = _now()
    p = progress_path(out)
    p.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def mark(stage: str, *, reports_dir: Path | None = None, error: str | None = None) -> dict[str, Any]:
    st = load_progress(reports_dir)
    st["stage"] = stage
    if error:
        st.setdefault("errors", []).append({"stage": stage, "error": error, "at": _now()})
    else:
        done = list(st.get("completed_stages") or [])
        if stage not in done:
            done.append(stage)
        st["completed_stages"] = done
        audits = list(st.get("completed_audits") or [])
        if stage not in audits:
            audits.append(stage)
        st["completed_audits"] = audits
        st["last_successful_operation"] = stage
    save_progress(st, reports_dir)
    return st


def log(msg: str) -> None:
    print(f"[PHASE31] {msg}", flush=True)
