"""Independent audit of Phase 59 artifacts — do not trust report prose alone."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase60.adapters import holdout_days, inventory, root_for_day
from phase60.constants import PHASE59_REPORTS, SYMBOL, canonical_json_sha256, file_sha256


def _load(name: str) -> dict[str, Any] | None:
    p = PHASE59_REPORTS / name
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def run_independent_phase59_audit() -> dict[str, Any]:
    inv_live = inventory()
    cov = _load("data_coverage_manifest.json") or {}
    integ = _load("dataset_integrity.json") or {}
    integ_full = _load("dataset_integrity_full.json") or {}
    inv_art = _load("dataset_inventory.json") or {}
    final = PHASE59_REPORTS / "FINAL_REPORT.md"

    union_live = list(inv_live.get("union_days") or [])
    union_art = list(inv_art.get("union_days") or [])
    deep = list(cov.get("deep_tick_audit_days") or [])
    remaining_reported = list(cov.get("union_days_not_in_deep_audit") or [])
    remaining_computed = sorted(set(union_live) - set(deep))

    # Locate each remaining day in archives
    remaining_status = []
    for day in remaining_computed:
        root = root_for_day(day)
        m5 = None
        ticks_n_hours = 0
        if root is not None:
            m5_path = root / "m5" / f"m5_{SYMBOL}_{day}.jsonl"
            m5 = m5_path.is_file()
            tick_root = root / "ticks"
            if tick_root.is_dir():
                ticks_n_hours = len(list(tick_root.glob(f"ticks_{SYMBOL}_{day}_*h.jsonl")))
        remaining_status.append(
            {
                "day": day,
                "resolved_root": str(root) if root else None,
                "m5_present": bool(m5),
                "tick_hour_files": ticks_n_hours,
                "locatable": root is not None and bool(m5),
                "reason_if_unlocatable": None
                if (root is not None and bool(m5))
                else "missing_m5_or_root",
            }
        )

    checks = {
        "union_n_days_matches_100": len(union_live) == 100 and inv_live.get("union_n_days") == 100,
        "union_membership_matches_artifact": union_live == union_art,
        "deep_audit_n_90": len(deep) == 90 and cov.get("deep_tick_audit_days_n") == 90,
        "remaining_n_10": len(remaining_computed) == 10,
        "remaining_matches_manifest": remaining_computed == remaining_reported,
        "integrity_bars_24560": integ.get("total_m5_bars") == 24560,
        "integrity_ticks_23736188": integ.get("total_ticks") == 23736188,
        "integrity_ok_90": integ.get("n_ok") == 90 and integ.get("n_days") == 90,
        "gap_days_n_9": integ.get("n_gap_days") == 9,
        "holdout_10_sealed": len(holdout_days()) == 10,
        "coverage_sha_present": bool(cov.get("coverage_sha256")),
        "integrity_sha_present": bool(integ.get("integrity_sha256")),
        "final_report_exists": final.is_file(),
        "source_not_silently_repaired_claimed": cov.get("source_data_silently_repaired") is False,
    }

    # Recompute coverage sha from artifact body (excluding its own hash field)
    cov_body = {k: v for k, v in cov.items() if k != "coverage_sha256"}
    cov_sha_recomputed = canonical_json_sha256(cov_body) if cov else None
    checks["coverage_sha_reproducible"] = (
        cov_sha_recomputed == cov.get("coverage_sha256") if cov else False
    )

    integ_body = {k: v for k, v in integ.items() if k != "integrity_sha256"}
    # integrity summary excludes rows; full has rows — verify summary fields vs full
    checks["integrity_summary_vs_full_bars"] = integ.get("total_m5_bars") == integ_full.get(
        "total_m5_bars"
    )
    checks["integrity_summary_vs_full_ticks"] = integ.get("total_ticks") == integ_full.get(
        "total_ticks"
    )

    artifact_hashes = {
        name: file_sha256(PHASE59_REPORTS / name)
        for name in (
            "data_coverage_manifest.json",
            "dataset_integrity.json",
            "dataset_integrity_full.json",
            "dataset_inventory.json",
            "spread_distributions.json",
            "execution_stress.json",
            "validation_results.json",
            "FINAL_REPORT.md",
        )
    }

    out = {
        "phase59_reports_dir": str(PHASE59_REPORTS),
        "checks": checks,
        "all_critical_checks_pass": all(
            checks[k]
            for k in (
                "union_n_days_matches_100",
                "deep_audit_n_90",
                "remaining_n_10",
                "remaining_matches_manifest",
                "integrity_bars_24560",
                "integrity_ticks_23736188",
                "holdout_10_sealed",
            )
        ),
        "union_n_days_live": len(union_live),
        "union_date_min": inv_live.get("date_min"),
        "union_date_max": inv_live.get("date_max"),
        "deep_tick_audit_days_n": len(deep),
        "remaining_10_days": remaining_computed,
        "remaining_day_status": remaining_status,
        "all_remaining_locatable": all(r["locatable"] for r in remaining_status),
        "integrity_reported": {
            "n_days": integ.get("n_days"),
            "n_ok": integ.get("n_ok"),
            "total_m5_bars": integ.get("total_m5_bars"),
            "total_ticks": integ.get("total_ticks"),
            "n_gap_days": integ.get("n_gap_days"),
            "n_dup_ts_days": integ.get("n_dup_ts_days"),
            "n_ohlc_error_days": integ.get("n_ohlc_error_days"),
        },
        "coverage_sha256_artifact": cov.get("coverage_sha256"),
        "coverage_sha256_recomputed": cov_sha_recomputed,
        "artifact_file_sha256": artifact_hashes,
        "limitations": [
            "Phase59 deep audit preferred phase43/49/53 (+holdout); phase38-only sparse days deferred",
            "Independent audit verifies artifact consistency; full tick recount of 90 days not re-run here",
            "Reported tick/bar totals trusted after summary↔full consistency; remaining 10 audited in Phase60",
        ],
        "note": "Do not treat remaining 10 as audited until Phase60 deep audit completes",
    }
    out["audit_sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "audit_sha256"})
    return out
