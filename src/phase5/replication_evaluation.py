"""Evaluate frozen NY-SELL only. No extra subgroups."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from phase5.constants import PHASE4_REFERENCE, TIME_FORMAT
from phase5.statistics import bootstrap_mean_r, concentration, cost_stress, trade_metrics


def eligible_sells(outcomes: list[dict]) -> list[dict]:
    return [r for r in outcomes if r.get("eligible") and r.get("net_r") != ""]


def arrays(rows: list[dict]):
    r = np.array([float(x["net_r"]) for x in rows], dtype=float)
    pnl = np.array([float(x["net_pnl"]) for x in rows], dtype=float)
    times = [x["decision_time"] for x in rows]
    return r, pnl, times


def chronological_blocks(rows: list[dict]) -> dict:
    """Equal-duration thirds of [min, max] decision_time. Formula frozen in the hypothesis."""
    if not rows:
        return {"early": {"n": 0}, "middle": {"n": 0}, "late": {"n": 0}}
    dts = [datetime.strptime(x["decision_time"], TIME_FORMAT) for x in rows]
    start, end = min(dts), max(dts)
    span = end - start
    b1 = start + span / 3
    b2 = start + 2 * span / 3
    buckets = {"early": [], "middle": [], "late": []}
    for rec, t in zip(rows, dts):
        if t < b1:
            buckets["early"].append(rec)
        elif t < b2:
            buckets["middle"].append(rec)
        else:
            buckets["late"].append(rec)
    out = {
        "boundaries": {
            "start": start.strftime(TIME_FORMAT),
            "early_end_exclusive": b1.strftime(TIME_FORMAT),
            "middle_end_exclusive": b2.strftime(TIME_FORMAT),
            "end": end.strftime(TIME_FORMAT),
            "rule": "equal duration thirds of eligible NY-SELL decision_time range",
        }
    }
    signs = []
    for name, part in buckets.items():
        rr, pnl, times = arrays(part) if part else (np.array([]), np.array([]), [])
        met = trade_metrics(rr, pnl)
        met["first"] = part[0]["decision_time"] if part else None
        met["last"] = part[-1]["decision_time"] if part else None
        out[name] = met
        if met["n"] and np.isfinite(met["mean_r"]):
            signs.append(met["mean_r"] > 0)
    out["n_positive_blocks"] = int(sum(signs))
    out["n_blocks_with_trades"] = int(len(signs))
    out["all_blocks_positive"] = bool(len(signs) == 3 and all(signs))
    out["sign_reversal"] = bool(len(signs) >= 2 and (any(signs) and not all(signs)))
    return out


def classify(pooled: dict, blocks: dict, boot: dict, stress: dict, conc: dict, quality_ok: bool) -> str:
    if not quality_ok:
        return "REPLICATION INCOMPLETE"
    mean_r = pooled.get("mean_r")
    pf = pooled.get("profit_factor")
    if pooled.get("n", 0) == 0 or mean_r is None or not np.isfinite(mean_r):
        return "REPLICATION INCOMPLETE"
    x15 = (stress.get("spread_x1.5") or {}).get("mean_r")
    ci_low = boot.get("ci_low")
    p_le0 = boot.get("p_mean_le_0")
    concentrated = False
    if conc.get("top_1pct_share_of_total_r") is not None and np.isfinite(conc["top_1pct_share_of_total_r"]):
        concentrated = abs(conc["top_1pct_share_of_total_r"]) >= 0.50
    collapse = bool(blocks.get("sign_reversal"))

    if mean_r <= 0 or (np.isfinite(pf) and pf <= 1) or (x15 is not None and np.isfinite(x15) and x15 <= 0):
        return "NOT REPLICATED"

    supportive = (
        ci_low is not None and np.isfinite(ci_low) and ci_low > 0
        and p_le0 is not None and p_le0 < 0.025
    )
    if (
        mean_r > 0
        and np.isfinite(pf) and pf > 1
        and x15 is not None and np.isfinite(x15) and x15 > 0
        and not concentrated
        and not collapse
        and supportive
        and quality_ok
    ):
        return "REPLICATED / POTENTIALLY CREDIBLE"
    return "PROMISING BUT UNCONFIRMED"


def evaluate(outcomes: list[dict], quality_ok: bool) -> dict:
    rows = eligible_sells(outcomes)
    r, pnl, times = arrays(rows) if rows else (np.array([]), np.array([]), [])
    pooled = trade_metrics(r, pnl)
    pooled["eligible_observations"] = len(rows)
    pooled["ny_sell_rows_including_ineligible"] = len(outcomes)
    boot = bootstrap_mean_r(times, r) if len(r) else {
        "mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
        "p_mean_le_0": float("nan"), "n_days": 0, "n_samples": 2000, "seed": 42, "method": "day_cluster",
    }
    stress = cost_stress(pnl, r) if len(r) else {}
    conc = concentration(times, r, pnl)
    blocks = chronological_blocks(rows)
    label = classify(pooled, blocks, boot, stress, conc, quality_ok)
    return {
        "pooled": pooled,
        "blocks": blocks,
        "bootstrap": boot,
        "cost_stress": stress,
        "concentration": conc,
        "phase4_reference": PHASE4_REFERENCE,
        "classification": label,
        "pooled_with_phase4": False,
        "filters_added": False,
    }
