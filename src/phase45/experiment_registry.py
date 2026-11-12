"""Consolidated experiment registry from reloaded phase artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase45.constants import (
    PHASE42_REJECTED_PREFIX,
    PHASE44_REJECTED_PREFIX,
    PROJECT_ROOT,
    REPORTS_ROOT,
    RETIRED_STRATEGIES,
    SRC_DIR,
)
from phase45.progress import write_json
from phase45.scan_verdicts import scan_final_verdicts


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _strategies_phase25() -> list[dict[str, Any]]:
    p = SRC_DIR / "phase25" / "constants.py"
    out = []
    if not p.is_file():
        return out
    # Import read-only
    from phase25.constants import STRATEGY_PARAMS

    for sid, params in STRATEGY_PARAMS.items():
        out.append(
            {
                "id": sid,
                "family": "phase25_strategy_discovery",
                "source_phase": "phase25",
                "source_file": "src/phase25/constants.py",
                "parameters": dict(params),
                "status": "retired" if sid in RETIRED_STRATEGIES or sid == "mean_reversion" else "historical",
            }
        )
    return out


def _h13_entry() -> dict[str, Any]:
    from phase16a.constants import FROZEN_CUTS

    return {
        "id": "H13_C",
        "family": "h1_pullback_to_ema",
        "source_phases": ["phase14", "phase16a", "phase35", "phase39", "phase41"],
        "cuts": dict(FROZEN_CUTS),
        "status": "RETIRED",
        "do_not_revive": True,
        "evidence_files": [
            "src/phase16a/constants.py",
            "reports/phase41/candidate_verdicts.json",
            "reports/phase39/final_verdict.json",
        ],
    }


def _phase36_mr() -> dict[str, Any]:
    reg = _read_json(REPORTS_ROOT / "phase36" / "frozen_experiment_registry.json") or {}
    return {
        "id": "mean_reversion",
        "family": "zscore_rsi_vol_filter",
        "source_phases": ["phase25", "phase36", "phase39", "phase41"],
        "parameters": reg.get("parameters"),
        "status": "RETIRED",
        "do_not_revive": True,
        "phase36_verdict_file": "reports/phase36/final_verdict.json",
        "phase41_verdict": "EDGE_REJECTED",
    }


def _phase42_hyps() -> list[dict[str, Any]]:
    reg = _read_json(REPORTS_ROOT / "phase42" / "frozen_hypothesis_registry.json") or {}
    rejected = _read_json(REPORTS_ROOT / "phase42" / "rejected_hypothesis_registry.json") or {}
    rej_map = {r["hypothesis_id"]: r.get("reasons") for r in (rejected.get("rejected") or [])}
    out = []
    for h in reg.get("hypotheses") or []:
        hid = h.get("id")
        out.append(
            {
                "id": hid,
                "family": h.get("family"),
                "source_phase": "phase42",
                "status": "REJECTED",
                "do_not_revive": True,
                "prefix": PHASE42_REJECTED_PREFIX,
                "rejection_reasons": rej_map.get(hid),
                "horizon_bars": h.get("horizon_bars"),
                "decision_side": h.get("decision_side"),
            }
        )
    return out


def _phase44_hyps() -> list[dict[str, Any]]:
    reg = _read_json(REPORTS_ROOT / "phase44" / "frozen_hypothesis_registry_pre_discovery.json") or {}
    disc = _read_json(REPORTS_ROOT / "phase44" / "discovery_results.json") or {}
    rej_map = {r["hypothesis_id"]: r.get("reasons") for r in (disc.get("rejected") or [])}
    out = []
    for h in reg.get("hypotheses") or []:
        hid = h.get("id")
        out.append(
            {
                "id": hid,
                "family": h.get("family"),
                "source_phase": "phase44",
                "status": "REJECTED",
                "do_not_revive": True,
                "prefix": PHASE44_REJECTED_PREFIX,
                "rejection_reasons": rej_map.get(hid),
                "horizon_bars": h.get("horizon_bars"),
            }
        )
    return out


def build_experiment_registry() -> dict[str, Any]:
    verdicts = scan_final_verdicts(REPORTS_ROOT)
    strategies = [_h13_entry(), _phase36_mr()] + _strategies_phase25()
    # dedupe mean_reversion from STRATEGY_PARAMS if present
    seen = set()
    uniq = []
    for s in strategies:
        if s["id"] in seen:
            continue
        seen.add(s["id"])
        uniq.append(s)

    hypotheses = _phase42_hyps() + _phase44_hyps()

    # Overlap / duplicate research themes
    overlaps = [
        {
            "theme": "H13_C pullback evaluation",
            "phases": ["phase14", "phase16a", "phase25", "phase29", "phase35", "phase39", "phase41"],
            "information_gain_assessment": "LOW after Phase41 full-session retest — retired",
        },
        {
            "theme": "mean_reversion z/RSI",
            "phases": ["phase25", "phase35", "phase36", "phase39", "phase41"],
            "information_gain_assessment": "LOW after Phase41 EDGE_REJECTED on full-session ticks",
        },
        {
            "theme": "indicator-family hypothesis screens",
            "phases": ["phase42", "phase44"],
            "information_gain_assessment": (
                "MODERATE process gain (protocol + independent dates) but ZERO surviving predictive edges; "
                "repeated family screens without new information ontology"
            ),
        },
        {
            "theme": "historical bid/ask acquisition",
            "phases": ["phase33", "phase34", "phase35", "phase36", "phase37", "phase38", "phase40", "phase43"],
            "information_gain_assessment": "HIGH for data readiness; necessary but not sufficient for edge",
        },
    ]

    payload = {
        "n_phase_verdicts_reloaded": len(verdicts),
        "phase_verdicts": verdicts,
        "strategies": uniq,
        "hypotheses": hypotheses,
        "n_strategies": len(uniq),
        "n_hypotheses": len(hypotheses),
        "retired_do_not_revive": list(RETIRED_STRATEGIES) + [h["id"] for h in hypotheses],
        "research_overlaps": overlaps,
        "evidence_root": str(REPORTS_ROOT).replace("\\", "/"),
        "note": "Registry rebuilt by reloading JSON artifacts from disk; historical results not modified.",
    }
    write_json("consolidated_experiment_registry.json", payload)
    return payload
