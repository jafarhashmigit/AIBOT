"""Incremental Phase 28 reports (no statistical validation claims from small n)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aibot_time import display_pkt, display_utc, display_utc_iso, storage_utc_iso
from phase28.campaign import CampaignStore, evidence_status
from phase28.constants import (
    OBSERVER_BASELINE,
    OBSERVER_HIGH_VOL,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
)
from phase28.journals import ObserverJournal, OutcomeStore
from phase28.outcomes import summarize_outcomes


def _mean_ci(xs: list[float]) -> dict[str, Any]:
    n = len(xs)
    if n == 0:
        return {"n": 0, "mean": None, "se": None, "ci95": None, "note": "empty"}
    mean = sum(xs) / n
    if n < 2:
        return {"n": n, "mean": mean, "se": None, "ci95": None, "note": "n<2"}
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    se = math.sqrt(var / n)
    return {
        "n": n,
        "mean": mean,
        "se": se,
        "ci95": [mean - 1.96 * se, mean + 1.96 * se],
        "note": "Normal approx; not a validation claim.",
    }


def _realized_r_h12(outcome_rows: list[dict[str, Any]]) -> list[float]:
    out = []
    for r in outcome_rows:
        if r.get("horizon_id") != "H12":
            continue
        if r.get("status") in {None, "PENDING", ""}:
            continue
        try:
            out.append(float(r["realized_r"]))
        except (TypeError, ValueError, KeyError):
            continue
    return out


def observer_snapshot(root: Path, observer_id: str) -> dict[str, Any]:
    oroot = Path(root) / "observers" / observer_id
    decisions = ObserverJournal(oroot, observer_id).read_all()
    outcomes = OutcomeStore(oroot, observer_id).read_all()
    actions = [str(d.get("experimental_action", "")).upper() for d in decisions]
    h13c = [str(d.get("h13c_experimental_action", "")).upper() for d in decisions]
    accepted = [d for d in decisions if d.get("accepted")]
    skipped = [
        d
        for d in decisions
        if str(d.get("h13c_experimental_action", "")).upper() in {"BUY", "SELL"} and not d.get("accepted")
    ]
    rs = _realized_r_h12(outcomes)
    days = sorted({(d.get("decision_timestamp_utc") or "")[:10] for d in decisions if d.get("decision_timestamp_utc")})
    return {
        "observer_id": observer_id,
        "n_decisions": len(decisions),
        "n_buy": sum(1 for a in actions if a == "BUY"),
        "n_sell": sum(1 for a in actions if a == "SELL"),
        "n_wait": sum(1 for a in actions if a == "WAIT"),
        "n_h13c_buy_sell": sum(1 for a in h13c if a in {"BUY", "SELL"}),
        "n_accepted": len(accepted),
        "n_skipped_policy": len(skipped),
        "outcomes": summarize_outcomes(outcomes),
        "h12_performance": _mean_ci(rs),
        "n_distinct_days": len([d for d in days if d]),
        "reason_code_counts": _count_field(decisions, "reason_code"),
        "regime_counts": _count_field(decisions, "pred_vol_regime"),
    }


def _count_field(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        k = str(r.get(key) or "null")
        out[k] = out.get(k, 0) + 1
    return out


def build_campaign_report(
    *,
    root: Path,
    session: dict[str, Any] | None = None,
    integrity: dict[str, Any] | None = None,
    gaps: int = 0,
) -> dict[str, Any]:
    camp = CampaignStore(root).status_view()
    base = observer_snapshot(root, OBSERVER_BASELINE)
    high = observer_snapshot(root, OBSERVER_HIGH_VOL)
    ev = evidence_status(
        n_candles=int(camp.get("new_candles_processed") or 0),
        n_baseline_decisions=int(base.get("n_h13c_buy_sell") or 0),
        n_high_accepted=int(high.get("n_accepted") or 0),
        n_matured_h12=int((high.get("outcomes") or {}).get("n_matured_h12") or 0),
        n_days=max(int(base.get("n_distinct_days") or 0), int(high.get("n_distinct_days") or 0)),
    )
    now = datetime.now(timezone.utc)
    return {
        "recipe_id": RECIPE_ID,
        "phase": "28",
        "generated_at_utc": storage_utc_iso(now),
        "generated_at_display": display_utc_iso(now),
        "generated_at_pkt_display": display_pkt(now),
        "mode": (session or {}).get("mode") or "report",
        "campaign": camp,
        "forward_observation_start_utc": camp.get("forward_observation_start_utc"),
        "forward_observation_start_display": (
            display_utc(camp["forward_observation_start_utc"])
            if camp.get("forward_observation_start_utc")
            else None
        ),
        "last_candle_close_display": (
            display_utc(camp["last_candle_close_utc"]) if camp.get("last_candle_close_utc") else None
        ),
        "genuinely_new_forward_candles": camp.get("new_candles_processed"),
        "data_gaps": gaps,
        "observers": {
            OBSERVER_BASELINE: base,
            OBSERVER_HIGH_VOL: high,
        },
        "comparison": {
            "baseline_h12": base.get("h12_performance"),
            "high_only_h12": high.get("h12_performance"),
            "note": (
                "Show sample sizes and uncertainty; do not claim validation from small forward n. "
                f"Evidence status: {ev['status']}."
            ),
        },
        "evidence": ev,
        "session": session,
        "integrity": integrity,
        "production_final_action": PRODUCTION_FINAL_ACTION,
        "champion_status": "NO_MODEL",
        "h13c_status": "EXPERIMENTAL",
        "insufficient_forward_evidence": ev["status"] == "INSUFFICIENT_FORWARD_EVIDENCE",
    }
