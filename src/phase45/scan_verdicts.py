"""Reload phase final_verdict artifacts from disk (independent of summaries)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def scan_final_verdicts(reports_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in sorted(reports_root.glob("phase*/final_verdict.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            rows.append({"phase": p.parent.name, "error": str(exc), "path": str(p)})
            continue
        v = d.get("final_verdict") or d.get("verdict")
        if not v and isinstance(d.get("verdicts"), dict):
            parts = []
            for k, vv in d["verdicts"].items():
                if isinstance(vv, dict):
                    parts.append(f"{k}:{vv.get('verdict')}")
            v = " | ".join(parts)
        rows.append(
            {
                "phase": p.parent.name,
                "path": str(p).replace("\\", "/"),
                "final_verdict": v,
                "champion": d.get("champion") or d.get("champion_status") or d.get("CHAMPION_STATUS"),
                "production": d.get("production") or d.get("production_final_action") or d.get("PRODUCTION_FINAL_ACTION"),
                "best_candidate": d.get("best_candidate"),
                "sha256_keys_present": sorted(d.keys())[:20],
            }
        )
    return rows
