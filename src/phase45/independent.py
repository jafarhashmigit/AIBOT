"""Independent verification — reload source artifacts; do not trust in-memory copies alone."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase45.constants import REPORTS_DIR, REPORTS_ROOT
from phase45.scan_verdicts import scan_final_verdicts


def verify_independent(registry: dict[str, Any]) -> dict[str, Any]:
    # Reload verdicts fresh from disk
    fresh = scan_final_verdicts(REPORTS_ROOT)
    primary = registry.get("phase_verdicts") or []
    mismatches = []
    for a, b in zip(primary, fresh):
        if a.get("phase") != b.get("phase") or a.get("final_verdict") != b.get("final_verdict"):
            mismatches.append({"primary": a, "fresh": b})
    # Reload Phase41/42/44 key rejection artifacts
    checks = {}
    for rel in (
        "phase41/candidate_verdicts.json",
        "phase42/rejected_hypothesis_registry.json",
        "phase44/discovery_results.json",
        "phase43/final_verdict.json",
        "phase42/experience_stores.json",
        "phase44/experience_stores.json",
    ):
        p = REPORTS_ROOT / rel
        checks[rel] = {"exists": p.is_file(), "bytes": p.stat().st_size if p.is_file() else 0}

    # Confirm Phase45 outputs written
    out_checks = {}
    for name in (
        "consolidated_experiment_registry.json",
        "research_failure_taxonomy.json",
        "architecture_gap_analysis.json",
        "strategic_roadmap.json",
    ):
        p = REPORTS_DIR / name
        out_checks[name] = p.is_file()

    return {
        "ok": len(mismatches) == 0 and all(out_checks.values()),
        "verdict_reload_n": len(fresh),
        "verdict_mismatches": mismatches[:10],
        "artifact_checks": checks,
        "phase45_output_checks": out_checks,
        "method": "fresh disk reload of final_verdict.json files + presence checks",
    }
