"""Phase 29 incremental reports — no edge claims from thin samples."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aibot_time import display_pkt, display_utc, display_utc_iso, storage_utc_iso
from phase28.journals import ObserverJournal, OutcomeStore
from phase29.campaign import CampaignStore, evidence_status
from phase29.constants import OBSERVER_A, OBSERVER_B, PRODUCTION_FINAL_ACTION, RECIPE_ID
from phase29.outcomes import summarize_outcomes


def _mean_ci(xs: list[float]) -> dict[str, Any]:
    n = len(xs)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "se": None, "ci95": None}
    xs_sorted = sorted(xs)
    mean = sum(xs) / n
    mid = n // 2
    median = xs_sorted[mid] if n % 2 else 0.5 * (xs_sorted[mid - 1] + xs_sorted[mid])
    if n < 2:
        return {"n": n, "mean": mean, "median": median, "se": None, "ci95": None}
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    se = math.sqrt(var / n)
    return {"n": n, "mean": mean, "median": median, "se": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def _profit_factor(xs: list[float]) -> float | None:
    gains = sum(x for x in xs if x > 0)
    losses = sum(-x for x in xs if x < 0)
    if losses <= 0:
        return None if gains <= 0 else float("inf")
    return gains / losses


def _max_dd(xs: list[float]) -> float | None:
    if not xs:
        return None
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in xs:
        equity += x
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def observer_snapshot(root: Path, observer_id: str) -> dict[str, Any]:
    oroot = Path(root) / "observers" / observer_id
    decisions = ObserverJournal(oroot, observer_id).read_all()
    outcomes = OutcomeStore(oroot, observer_id).read_all()
    actions = [str(d.get("experimental_action", "")).upper() for d in decisions]
    accepted = [d for d in decisions if d.get("accepted")]
    rs = []
    for r in outcomes:
        if r.get("horizon_id") != "H12" or r.get("status") in {None, "PENDING", ""}:
            continue
        try:
            rs.append(float(r["realized_r"]))
        except (TypeError, ValueError, KeyError):
            continue
    wins = sum(1 for x in rs if x > 0)
    return {
        "observer_id": observer_id,
        "n_decisions": len(decisions),
        "n_buy": sum(1 for a in actions if a == "BUY"),
        "n_sell": sum(1 for a in actions if a == "SELL"),
        "n_wait": sum(1 for a in actions if a == "WAIT"),
        "n_accepted": len(accepted),
        "signal_rate": (len(accepted) / len(decisions)) if decisions else 0.0,
        "outcomes": summarize_outcomes(outcomes),
        "h12_performance": {
            **_mean_ci(rs),
            "win_rate": (wins / len(rs)) if rs else None,
            "profit_factor": _profit_factor(rs),
            "max_drawdown_r": _max_dd(rs),
            "note": "Sample stats only; not a production edge claim.",
        },
    }


def build_campaign_report(
    *,
    root: Path,
    session: dict[str, Any] | None = None,
    integrity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    camp = CampaignStore(root).status_view()
    base = observer_snapshot(root, OBSERVER_A)
    high = observer_snapshot(root, OBSERVER_B)
    n_buy_sell = int(base["n_buy"]) + int(base["n_sell"])
    n_matured = int((base.get("outcomes") or {}).get("n_matured") or 0)
    ev = evidence_status(
        n_candles=int(camp.get("new_candles_processed") or 0),
        n_buy_sell=n_buy_sell,
        n_matured=n_matured,
    )
    now = datetime.now(timezone.utc)
    fwd = camp.get("forward_observation_start_utc")
    last = camp.get("last_candle_close_utc")
    return {
        "recipe_id": RECIPE_ID,
        "phase": "29",
        "generated_at_utc": storage_utc_iso(now),
        "generated_at_display": display_utc_iso(now),
        "generated_at_pkt_display": display_pkt(now),
        "mode": (session or {}).get("mode") or "report",
        "campaign": camp,
        "forward_observation_start_utc": fwd,
        "forward_observation_start_display": display_utc(fwd) if fwd else None,
        "last_candle_close_display": display_utc(last) if last else None,
        "genuinely_new_forward_candles": camp.get("new_candles_processed"),
        "observers": {OBSERVER_A: base, OBSERVER_B: high},
        "comparison": {
            "baseline_h12": base.get("h12_performance"),
            "high_only_h12": high.get("h12_performance"),
            "phase28_note": "Phase 28 ended with 100 forward candles, 0 BUY/SELL, INSUFFICIENT_FORWARD_EVIDENCE.",
            "phase27_note": "High-only remains research-only; no production promotion.",
        },
        "evidence": ev,
        "session": session,
        "integrity": integrity,
        "production_final_action": PRODUCTION_FINAL_ACTION,
        "champion_status": "NO_MODEL",
        "h13c_status": "EXPERIMENTAL",
        "insufficient_forward_evidence": ev["status"] == "INSUFFICIENT_FORWARD_EVIDENCE",
        "broker_orders": 0,
        "holdout_accessed": False,
    }
