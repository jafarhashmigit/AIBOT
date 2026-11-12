"""Phase 31 preflight — verify Phase30 evidence + safety without opening holdout."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase31.constants import (
    HOLDOUT_NAME,
    PHASE30_EXPECTED,
    PHASE30_SUMMARY,
    RECIPE_ID,
    RESEARCH_CUTOFF_UTC,
)
from phase31.integrity import safety_snapshot


def _approx(a: float | None, b: float | None, tol: float = 1e-9) -> bool:
    if a is None or b is None:
        return a is b
    return abs(float(a) - float(b)) <= tol


def verify_phase30_figures(summary: dict[str, Any]) -> dict[str, Any]:
    checks = {}
    h = summary["h13c_benchmark"]["metrics"]["score"]["pooled"]
    exp = PHASE30_EXPECTED["h13c"]
    checks["h13c"] = {
        "n_match": int(h["n"]) == exp["n"],
        "mean_r_match": _approx(h["mean_r"], exp["mean_r"]),
        "pf_match": _approx(h["profit_factor"], exp["pf"]),
        "observed": {"n": h["n"], "mean_r": h["mean_r"], "pf": h["profit_factor"]},
        "expected": exp,
    }
    for sid in ("vol_norm_momentum", "m15_trend_m5_trigger", "robust_mad_reversion"):
        b = summary["strategies"][sid]
        p = b["metrics"]["score"]["pooled"]
        e = PHASE30_EXPECTED[sid]
        checks[sid] = {
            "n_match": int(p["n"]) == e["n"],
            "mean_r_match": _approx(p["mean_r"], e["mean_r"]),
            "pf_match": _approx(p["profit_factor"], e["pf"]),
            "observed": {"n": p["n"], "mean_r": p["mean_r"], "pf": p["profit_factor"]},
            "expected": e,
        }
    # Diversity claims
    pos = sum(
        1
        for sid, bl in summary["strategies"].items()
        if bl["metrics"]["mean_r"] is not None
        and bl["metrics"]["mean_r"] == bl["metrics"]["mean_r"]
        and bl["metrics"]["mean_r"] > 0
    )
    checks["no_positive_pooled_mean_r"] = pos == 0
    checks["phase_verdict"] = summary.get("phase_verdict")
    checks["all_verified"] = all(
        v.get("n_match") and v.get("mean_r_match") and v.get("pf_match")
        for k, v in checks.items()
        if isinstance(v, dict) and "n_match" in v
    ) and checks["no_positive_pooled_mean_r"]
    return checks


def run_preflight() -> dict[str, Any]:
    safety = safety_snapshot()
    missing = []
    phase30 = None
    phase30_verify = None
    if not PHASE30_SUMMARY.exists():
        missing.append(str(PHASE30_SUMMARY))
    else:
        phase30 = json.loads(PHASE30_SUMMARY.read_text(encoding="utf-8"))
        phase30_verify = verify_phase30_figures(phase30)

    if safety["holdout_accessed"]:
        raise RuntimeError("HARD FAILURE: holdout access counter non-zero")
    if HOLDOUT_NAME in str(PHASE30_SUMMARY):
        raise RuntimeError("HARD FAILURE: holdout path referenced")

    out = {
        "recipe": RECIPE_ID,
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "safety": safety,
        "phase30_summary_path": str(PHASE30_SUMMARY) if PHASE30_SUMMARY.exists() else None,
        "phase30_verification": phase30_verify,
        "missing_artifacts": missing,
        "ok": bool(safety["protected_artifacts_intact"] and safety["cutoff_ok"] and not missing),
        "note": "Holdout file may exist on disk but must remain unopened.",
    }
    return out
