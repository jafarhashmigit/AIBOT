"""Progress checkpoints for Phase 32."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase32.constants import REPORTS_DIR

STAGES = [
    "preflight",
    "feature_recomputation",
    "feature_comparison",
    "full_label_reconstruction",
    "label_comparison",
    "trade_cost_reconciliation",
    "gross_net_analysis",
    "provider_investigation",
    "execution_realism",
    "statistical_validation",
    "final_verdict",
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"[PHASE32] {msg}", flush=True)


def load_progress(reports_dir: Path | None = None) -> dict[str, Any]:
    p = (reports_dir or REPORTS_DIR) / "progress.json"
    if not p.exists():
        return {
            "stage": "init",
            "completed_stages": [],
            "last_successful_operation": None,
            "errors": [],
            "remaining_stages": list(STAGES),
        }
    return json.loads(p.read_text(encoding="utf-8"))


def save_progress(state: dict[str, Any], reports_dir: Path | None = None) -> Path:
    out = reports_dir or REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    done = set(state.get("completed_stages") or [])
    state["remaining_stages"] = [s for s in STAGES if s not in done]
    state["updated_at_utc"] = _now()
    p = out / "progress.json"
    p.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def mark(stage: str, *, reports_dir: Path | None = None, error: str | None = None) -> None:
    st = load_progress(reports_dir)
    st["stage"] = stage
    if error:
        st.setdefault("errors", []).append({"stage": stage, "error": error, "at": _now()})
    else:
        done = list(st.get("completed_stages") or [])
        if stage not in done:
            done.append(stage)
        st["completed_stages"] = done
        st["last_successful_operation"] = stage
    save_progress(st, reports_dir)
