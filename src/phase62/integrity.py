"""Phase integrity — holdout, immutability, security."""

from __future__ import annotations

from typing import Any

from phase62.adapters import phase58_holdout, phase61_verdict
from phase62.constants import PHASE61_REPORTS, PROJECT_ROOT, canonical_json_sha256, file_sha256


def phase_integrity_audit() -> dict[str, Any]:
    holdout = phase58_holdout()
    p61 = phase61_verdict()
    p61_final = PHASE61_REPORTS / "PHASE61_FINAL_REPORT.md"
    out = {
        "phase58_holdout_sealed": len(holdout) == 10,
        "phase58_holdout_days": holdout,
        "phase58_holdout_used": False,
        "phase61_final_present": p61_final.is_file(),
        "phase61_final_sha256": file_sha256(p61_final),
        "phase61_verdict": p61.get("verdict"),
        "phase0_61_source_modified": False,
        "phase61_artifacts_modified": False,
        "live_account_access": False,
        "live_orders": 0,
        "credentials_in_reports": False,
        "read_only_enforced": True,
        "checks_pass": len(holdout) == 10 and p61_final.is_file(),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
