"""Pre-evaluation audit: freeze input hashes; stop on Phase40 drift."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase41.constants import (
    FROZEN_MEAN_REVERSION,
    H13C_FROZEN_CUTS,
    HORIZON_BARS,
    PHASE36_FROZEN,
    PHASE40_MANIFESTS,
    PHASE40_REPORTS,
    RECIPE_ID,
    SL_MULT,
    SYMBOL,
    TARGET_DATES,
    TP_MULT,
    file_sha256,
)
from phase41.progress import write_json


def _verify_phase40_unchanged() -> dict[str, Any]:
    """Recompute manifest file hashes and compare to Phase40 independent verification."""
    failures: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    if not PHASE40_MANIFESTS.is_dir():
        return {"ok": False, "reason": "phase40_manifests_missing", "files": [], "failures": []}

    for man in sorted(PHASE40_MANIFESTS.glob("*.manifest.json")):
        meta = json.loads(man.read_text(encoding="utf-8"))
        path = Path(meta["file_path"])
        expected = meta.get("sha256")
        row: dict[str, Any] = {
            "manifest": man.name,
            "path": str(path),
            "manifest_sha256": expected,
            "record_count": meta.get("record_count"),
        }
        if not path.is_file():
            row["ok"] = False
            row["error"] = "missing_data_file"
            failures.append(row)
        else:
            dig = file_sha256(path)
            row["recomputed_sha256"] = dig
            row["ok"] = dig == expected
            if not row["ok"]:
                row["error"] = "hash_mismatch"
                failures.append(row)
        files.append(row)

    indep_path = PHASE40_REPORTS / "independent_verification.json"
    indep_ok = None
    if indep_path.is_file():
        indep = json.loads(indep_path.read_text(encoding="utf-8"))
        indep_ok = bool(indep.get("ok"))
        if not indep_ok:
            failures.append({"error": "phase40_independent_verification_not_ok"})

    verdict_path = PHASE40_REPORTS / "final_verdict.json"
    p40_verdict = None
    if verdict_path.is_file():
        p40_verdict = json.loads(verdict_path.read_text(encoding="utf-8")).get("final_verdict")

    return {
        "ok": len(failures) == 0 and indep_ok is not False,
        "n_files": len(files),
        "n_failures": len(failures),
        "failures": failures[:30],
        "phase40_independent_ok": indep_ok,
        "phase40_final_verdict": p40_verdict,
        "files": files,
    }


def verify_and_freeze_specs() -> dict[str, Any]:
    discrepancies: list[str] = []
    p36: dict[str, Any] = {}
    if PHASE36_FROZEN.is_file():
        p36 = json.loads(PHASE36_FROZEN.read_text(encoding="utf-8"))
        params = p36.get("parameters") or {}
        for k, v in FROZEN_MEAN_REVERSION.items():
            if k not in params:
                discrepancies.append(f"Phase36 missing param {k}")
            elif params[k] != v:
                discrepancies.append(f"MR param mismatch {k}: phase25={v} phase36={params[k]}")
        exit_rules = p36.get("exit_rules") or {}
        if exit_rules.get("horizon_bars") != HORIZON_BARS:
            discrepancies.append(f"horizon mismatch: {HORIZON_BARS} vs {exit_rules.get('horizon_bars')}")
        if exit_rules.get("tp_atr_multiple") != TP_MULT:
            discrepancies.append(f"TP mismatch: {TP_MULT} vs {exit_rules.get('tp_atr_multiple')}")
        if exit_rules.get("sl_atr_multiple") != SL_MULT:
            discrepancies.append(f"SL mismatch: {SL_MULT} vs {exit_rules.get('sl_atr_multiple')}")
    else:
        discrepancies.append("Phase36 frozen_experiment_registry.json missing")

    # Exact H13 cuts from mission / Phase16A
    expected_low = -0.0010069324198160867
    expected_high = 0.0009989244530461683
    if H13C_FROZEN_CUTS.get("close_ema_low") != expected_low:
        discrepancies.append(f"H13 close_ema_low mismatch: {H13C_FROZEN_CUTS.get('close_ema_low')}")
    if H13C_FROZEN_CUTS.get("close_ema_high") != expected_high:
        discrepancies.append(f"H13 close_ema_high mismatch: {H13C_FROZEN_CUTS.get('close_ema_high')}")

    p40 = _verify_phase40_unchanged()
    if not p40["ok"]:
        discrepancies.append("Phase40 integrity check failed — evaluation blocked")

    spec = {
        "recipe_id": RECIPE_ID,
        "frozen_before_evaluation": True,
        "optimization_forbidden": True,
        "target_dates": TARGET_DATES,
        "symbol": SYMBOL,
        "discrepancies": discrepancies,
        "spec_ok": len(discrepancies) == 0,
        "phase40_integrity": {
            "ok": p40["ok"],
            "n_files": p40["n_files"],
            "n_failures": p40["n_failures"],
            "phase40_independent_ok": p40["phase40_independent_ok"],
            "phase40_final_verdict": p40["phase40_final_verdict"],
            "failure_sample": p40["failures"],
        },
        "candidates": {
            "H13_C": {
                "status": "PAUSED_FROZEN_BENCHMARK",
                "cuts": {
                    "close_ema_low": H13C_FROZEN_CUTS["close_ema_low"],
                    "close_ema_high": H13C_FROZEN_CUTS["close_ema_high"],
                    "q_low": H13C_FROZEN_CUTS.get("q_low"),
                    "q_high": H13C_FROZEN_CUTS.get("q_high"),
                    "train_cutoff": H13C_FROZEN_CUTS.get("train_cutoff"),
                },
                "rules": {
                    "BUY": "h1_trend==up AND close_to_ema_20<=close_ema_low AND ema_9_20_spread>0",
                    "SELL": "h1_trend==down AND close_to_ema_20>=close_ema_high AND ema_9_20_spread<0",
                },
                "execution": {
                    "entry": "next M5 open; BUY ask / SELL bid",
                    "exit": "BUY bid / SELL ask; TP 1.5 ATR; SL 1.0 ATR; horizon 12",
                },
                "h1_source": "Phase40 MT5 completed H1 warm-up bars (UTC)",
            },
            "mean_reversion": {
                "parameters": dict(FROZEN_MEAN_REVERSION),
                "rules": (p36.get("entry_rules") if p36 else {}),
                "execution": {
                    "entry": "next M5 open; BUY ask / SELL bid",
                    "exit": "BUY bid / SELL ask; TP 1.5 ATR; SL 1.0 ATR; horizon 12",
                    "source": "Phase36 frozen_experiment_registry.json + Phase25 STRATEGY_PARAMS",
                },
            },
        },
        "phase36_source_hashes": (p36.get("source_hashes") if p36 else {}),
        "input_file_hashes": p40["files"],
    }
    write_json("frozen_evaluation_manifest.json", spec)
    write_json("phase40_integrity_audit.json", p40)
    return spec
