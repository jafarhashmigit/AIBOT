"""Phase 33 preflight — branch, hashes, prior evidence, approved datasets."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from phase33.constants import (
    AGENT_SHADOW_DIR,
    CHAMPION_STATUS,
    HOLDOUT_NAME,
    H13_C_STATUS,
    MT5_FEATURES_PATH,
    PHASE25_RAW_DIR,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    PROTECTED_HASHES,
    RECIPE_ID,
    RESEARCH_CUTOFF_UTC,
    SRC_DIR,
    file_sha256,
)
from phase33.progress import write_json


def _git(cmd: list[str]) -> str:
    try:
        out = subprocess.check_output(
            ["git", *cmd],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.STDOUT,
            text=True,
        )
        return out.strip()
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"


def verify_protected_hashes() -> dict[str, Any]:
    results = {}
    intact = True
    for rel, expected in PROTECTED_HASHES.items():
        path = PROJECT_ROOT / rel
        if not path.is_file():
            results[rel] = {"status": "MISSING", "expected": expected}
            intact = False
            continue
        actual = file_sha256(path)
        ok = actual == expected
        if not ok:
            intact = False
        results[rel] = {
            "status": "OK" if ok else "MISMATCH",
            "expected": expected,
            "actual": actual,
        }
    return {"intact": intact, "files": results}


def inspect_phase24_provider() -> dict[str, Any]:
    """Read-only inspection of Phase 24 / Phase 25 Dukascopy research artifacts."""
    candidates = [
        PROJECT_ROOT / "reports" / "phase24" / "provider_qualification.json",
        PROJECT_ROOT / "reports" / "phase24" / "final_verdict.json",
        PROJECT_ROOT / "docs" / "agent" / "PHASE_25_DUKASCOPY_ACQUISITION.md",
        PROJECT_ROOT / "reports" / "phase25" / "final_verdict.json",
    ]
    found = []
    dukascopy_notes = []
    for p in candidates:
        if p.is_file():
            found.append(str(p.relative_to(PROJECT_ROOT)).replace("\\", "/"))
            text = p.read_text(encoding="utf-8", errors="replace")
            if "dukascopy" in text.lower() or "NOT_QUALIFIED" in text or "NOT_YET" in text:
                dukascopy_notes.append(
                    {
                        "path": str(p.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                        "snippet_present": True,
                    }
                )
    phase25_raw_exists = PHASE25_RAW_DIR.is_dir()
    phase25_days = []
    if phase25_raw_exists:
        phase25_days = sorted(d.name for d in PHASE25_RAW_DIR.iterdir() if d.is_dir())
    return {
        "evidence_class": "DIRECTLY_OBSERVED" if found else "UNVERIFIED",
        "artifact_paths": found,
        "phase25_raw_dir_exists": phase25_raw_exists,
        "phase25_raw_days": phase25_days,
        "notes": dukascopy_notes,
        "prior_status": "Phase24/25 documented Dukascopy bi5 as research source; full HISTORICAL_BID_ASK_QUALIFIED not established for strategy re-eval.",
    }


def inspect_phase32() -> dict[str, Any]:
    path = PROJECT_ROOT / "reports" / "phase32" / "final_verdict.json"
    if not path.is_file():
        return {"found": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "found": True,
        "path": "reports/phase32/final_verdict.json",
        "phase_verdict": data.get("phase_verdict"),
        "execution_realism": data.get("execution_realism"),
        "dukascopy_status": data.get("dukascopy_status"),
        "feature_ok": data.get("feature_ok"),
        "label_ok": data.get("label_ok"),
        "trade_ok": data.get("trade_ok"),
        "evidence_class": "DIRECTLY_OBSERVED",
    }


def approved_datasets() -> dict[str, Any]:
    mt5_ok = MT5_FEATURES_PATH.is_file()
    return {
        "mt5_features_utc_corrected": {
            "path": str(MT5_FEATURES_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "exists": mt5_ok,
            "role": "Approved historical MT5 mid/OHLC feature set (spread column present; bid/ask OHLC not separate).",
        },
        "holdout": {
            "name": HOLDOUT_NAME,
            "access": "FORBIDDEN",
            "accessed": False,
        },
        "phase25_dukascopy_raw": {
            "path": str(PHASE25_RAW_DIR.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "exists": PHASE25_RAW_DIR.is_dir(),
            "role": "Prior Phase25 bi5 sample — read-only reference for Phase33; not rewritten.",
        },
        "agent_shadow": {
            "path": str(AGENT_SHADOW_DIR.relative_to(PROJECT_ROOT)).replace("\\", "/") if AGENT_SHADOW_DIR.exists() else str(AGENT_SHADOW_DIR),
            "write_allowed": False,
        },
    }


def run_preflight() -> dict[str, Any]:
    branch = _git(["branch", "--show-current"])
    status = _git(["status", "-sb"])
    hashes = verify_protected_hashes()
    report = {
        "recipe_id": RECIPE_ID,
        "branch": branch,
        "git_status_short": status.splitlines()[:30],
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "h13_c": H13_C_STATUS,
        "protected_artifacts": hashes,
        "phase24_provider_research": inspect_phase24_provider(),
        "phase32_results": inspect_phase32(),
        "approved_datasets": approved_datasets(),
        "isolation": {
            "src_phase33_only_writes": True,
            "phase0_32_modification_forbidden": True,
            "mt5_connect": False,
            "discord": False,
            "telegram": False,
            "oci": False,
            "broker_orders": 0,
            "package_install": False,
            "git_commit": False,
            "git_push": False,
        },
        "ok": hashes["intact"] and PRODUCTION_FINAL_ACTION == "WAIT" and CHAMPION_STATUS == "NO_MODEL",
    }
    write_json("preflight.json", report)
    return report
