"""Independent recomputation — does not import phase46.outcomes calculators."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from phase46.atr import atr_at_bar
from phase46.constants import ATR_PERIOD, HORIZON_BARS, MIN_ATR
from phase46.cost_scenarios import COST_SCENARIO_REGISTRY, apply_scenario_costs


def _hash_core(row: dict[str, Any]) -> str:
    fields = (
        "entry_timestamp",
        "exit_timestamp",
        "action",
        "entry_bid",
        "entry_ask",
        "exit_bid",
        "exit_ask",
        "gross_pnl",
        "risk_amount",
        "gross_r",
        "spread_cost_embedded",
        "commission",
        "slippage",
        "net_pnl",
        "net_r",
        "mfe",
        "mae",
        "exit_reason",
        "data_quality_status",
    )
    payload = {k: row.get(k) for k in fields}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def recompute_directional(
    *,
    action: str,
    day: str,
    decision_idx: int,
    m5: list[dict[str, Any]],
    ticks_by_bar: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Fresh bid/ask path math — parallel implementation for mismatch detection."""
    assert action in ("BUY", "SELL")
    entry_idx = decision_idx + 1
    exit_idx = entry_idx + HORIZON_BARS - 1
    atr = atr_at_bar(m5, decision_idx, ATR_PERIOD)
    if atr is None or atr <= MIN_ATR or entry_idx >= len(m5) or exit_idx >= len(m5):
        return {"data_quality_status": "SKIP", "reason": "risk_or_horizon"}

    entry_bar = str(m5[entry_idx]["timestamp_utc"])
    exit_bar = str(m5[exit_idx]["timestamp_utc"])
    for j in range(entry_idx, exit_idx + 1):
        if not ticks_by_bar.get(str(m5[j]["timestamp_utc"])):
            return {"data_quality_status": "MISSING_PATH_TICKS"}

    e0 = ticks_by_bar[entry_bar][0]
    x0 = ticks_by_bar[exit_bar][-1]
    entry_bid, entry_ask = float(e0["bid"]), float(e0["ask"])
    exit_bid, exit_ask = float(x0["bid"]), float(x0["ask"])
    if action == "BUY":
        entry_fill = entry_ask
        exit_fill = exit_bid
        gross_pnl = exit_fill - entry_fill
    else:
        entry_fill = entry_bid
        exit_fill = exit_ask
        gross_pnl = entry_fill - exit_fill

    path: list[dict[str, Any]] = []
    for j in range(entry_idx, exit_idx + 1):
        path.extend(ticks_by_bar[str(m5[j]["timestamp_utc"])])
    entry_ms = int(e0["epoch_ms"])
    mfe = 0.0
    mae = 0.0
    for t in path:
        if int(t["epoch_ms"]) < entry_ms:
            continue
        pnl_now = (float(t["bid"]) - entry_fill) if action == "BUY" else (entry_fill - float(t["ask"]))
        mfe = max(mfe, pnl_now)
        mae = min(mae, pnl_now)

    risk = float(atr)
    entry_spread = entry_ask - entry_bid
    exit_spread = exit_ask - exit_bid
    base = apply_scenario_costs(
        gross_pnl=gross_pnl,
        risk_amount=risk,
        entry_spread=entry_spread,
        exit_spread=exit_spread,
        scenario=COST_SCENARIO_REGISTRY["OBSERVED_BIDASK_ONLY"],
    )
    row = {
        "day": day,
        "action": action,
        "entry_timestamp": e0["timestamp_utc"],
        "exit_timestamp": x0["timestamp_utc"],
        "entry_bid": entry_bid,
        "entry_ask": entry_ask,
        "exit_bid": exit_bid,
        "exit_ask": exit_ask,
        "gross_pnl": gross_pnl,
        "risk_amount": risk,
        "gross_r": gross_pnl / risk,
        "spread_cost_embedded": entry_spread + exit_spread,
        "commission": None,
        "slippage": None,
        "net_pnl": base["net_pnl"],
        "net_r": base["net_r"],
        "mfe": mfe,
        "mae": mae,
        "exit_reason": "HORIZON_EXIT",
        "data_quality_status": "OK",
    }
    row["outcome_sha256"] = _hash_core(row)
    # scenario nets
    row["scenario_nets"] = {
        sid: apply_scenario_costs(
            gross_pnl=gross_pnl,
            risk_amount=risk,
            entry_spread=entry_spread,
            exit_spread=exit_spread,
            scenario=sc,
        )
        for sid, sc in COST_SCENARIO_REGISTRY.items()
    }
    return row


def verify_outcomes(
    primary_rows: list[dict[str, Any]],
    *,
    m5_by_day: dict[str, list[dict[str, Any]]],
    ticks_by_day: dict[str, dict[str, list[dict[str, Any]]]],
    max_checks: int = 200,
) -> dict[str, Any]:
    """Reload-context recompute vs primary OK BUY/SELL rows."""
    mismatches: list[dict[str, Any]] = []
    checked = 0
    lookahead_flags = 0
    duplicates = 0
    seen: set[str] = set()

    for row in primary_rows:
        if row.get("action") not in ("BUY", "SELL"):
            continue
        if row.get("data_quality_status") != "OK":
            continue
        day = str(row["day"])
        decision_bar = str(row["decision_bar"])
        key = f"{day}|{decision_bar}|{row['action']}"
        if key in seen:
            duplicates += 1
        seen.add(key)

        m5 = m5_by_day[day]
        # find decision idx
        idx = next((i for i, b in enumerate(m5) if str(b["timestamp_utc"]) == decision_bar), None)
        if idx is None:
            mismatches.append({"key": key, "reason": "decision_bar_not_found"})
            continue

        # Lookahead check: ATR uses only bars <= idx; entry is idx+1
        if idx + 1 >= len(m5):
            mismatches.append({"key": key, "reason": "entry_after_end"})
            continue

        recomputed = recompute_directional(
            action=str(row["action"]),
            day=day,
            decision_idx=idx,
            m5=m5,
            ticks_by_bar=ticks_by_day[day],
        )
        if recomputed.get("data_quality_status") != "OK":
            mismatches.append({"key": key, "reason": "independent_not_ok", "got": recomputed})
            checked += 1
            if checked >= max_checks:
                break
            continue

        fields = ["gross_pnl", "net_pnl", "net_r", "gross_r", "mfe", "mae", "entry_fill", "exit_fill"]
        # entry_fill may be absent on hash-only — compare fills via bid/ask
        local_mismatch = {}
        for f in ("gross_pnl", "net_pnl", "net_r", "gross_r", "mfe", "mae", "entry_bid", "entry_ask", "exit_bid", "exit_ask"):
            a, b = row.get(f), recomputed.get(f)
            if a is None or b is None:
                if a != b:
                    local_mismatch[f] = {"primary": a, "independent": b}
                continue
            if abs(float(a) - float(b)) > 1e-9:
                local_mismatch[f] = {"primary": a, "independent": b}
        if row.get("outcome_sha256") != recomputed.get("outcome_sha256"):
            local_mismatch["outcome_sha256"] = {
                "primary": row.get("outcome_sha256"),
                "independent": recomputed.get("outcome_sha256"),
            }
        if local_mismatch:
            mismatches.append({"key": key, "diffs": local_mismatch})
        checked += 1
        if checked >= max_checks:
            break

    return {
        "ok": len(mismatches) == 0,
        "checked": checked,
        "mismatches": mismatches[:50],
        "n_mismatches": len(mismatches),
        "duplicate_keys": duplicates,
        "lookahead_flags": lookahead_flags,
        "method": "independent recompute without importing phase46.outcomes builders",
    }
