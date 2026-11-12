"""Regime robustness — report insufficiency rather than force conclusions."""

from __future__ import annotations

from typing import Any

from phase58.evaluation import calibrate
from phase65.evaluate import run_policy
from phase65.constants import canonical_json_sha256


def regime_robustness(
    hyp_id: str,
    events: list[dict[str, Any]],
    thr: dict[str, float],
) -> dict[str, Any]:
    dec = run_policy(events, hyp_id, thr)
    # attach atr for regime split
    atrs = [e["features"].get("atr") for e in events]
    valid_atr = [a for a in atrs if a is not None]
    if len(valid_atr) < 10:
        return {
            "hypothesis_id": hyp_id,
            "insufficient_sample": True,
            "note": "Too few events for regime splits",
            "sha256": "",
        }
    med = sorted(valid_atr)[len(valid_atr) // 2]
    high_idx = {i for i, e in enumerate(events) if (e["features"].get("atr") or 0) >= med}
    low_idx = {i for i, e in enumerate(events) if i not in high_idx}
    high = calibrate([dec[i] for i in range(len(dec)) if i in high_idx])
    low = calibrate([dec[i] for i in range(len(dec)) if i in low_idx])

    # session OPEN vs not
    open_idx = {i for i, e in enumerate(events) if e["features"].get("session_permits_new_entry")}
    open_cal = calibrate([dec[i] for i in range(len(dec)) if i in open_idx]) if open_idx else None
    closedish = calibrate([dec[i] for i in range(len(dec)) if i not in open_idx]) if len(open_idx) < len(dec) else None

    out = {
        "hypothesis_id": hyp_id,
        "insufficient_sample": False,
        "atr_median": med,
        "high_vol": {"n": high["n_decisions"], "mean": high["expected_net_r_all_decisions"]},
        "low_vol": {"n": low["n_decisions"], "mean": low["expected_net_r_all_decisions"]},
        "session_open": {"n": open_cal["n_decisions"], "mean": open_cal["expected_net_r_all_decisions"]} if open_cal else None,
        "session_not_open": {"n": closedish["n_decisions"], "mean": closedish["expected_net_r_all_decisions"]} if closedish else None,
        "general_xauusd_claim": False,
        "note": "Regime splits are descriptive; not independent confirmation",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
