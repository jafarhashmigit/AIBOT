"""Execution stress on non-holdout events — sensitivity only, not live cost truth."""

from __future__ import annotations

from typing import Any

from phase46.cost_scenarios import COST_SCENARIO_REGISTRY, apply_scenario_costs
from phase49.outcomes import build_outcome
from phase54.archive_loader import ticks_by_m5_bar
from phase54.constants import SYMBOL
from phase59.constants import canonical_json_sha256
from phase59.inventory import load_jsonl, resolve_root_for_day
from phase59.tick_stream import iter_tick_files


def _load_ticks_stream(root, day: str) -> list[dict[str, Any]]:
    ticks: list[dict[str, Any]] = []
    import json

    for p in iter_tick_files(root, day):
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ticks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return ticks


def _event_outcomes(days: list[str], *, stride: int = 36, max_per_day: int = 4) -> list[dict[str, Any]]:
    rows = []
    for day in days:
        root = resolve_root_for_day(day)
        if root is None:
            continue
        m5 = load_jsonl(root / "m5" / f"m5_{SYMBOL}_{day}.jsonl")
        ticks = _load_ticks_stream(root, day)
        by = ticks_by_m5_bar(ticks)
        first, last = 48, len(m5) - 13
        if last < first:
            continue
        n = 0
        idx = first
        while idx <= last and n < max_per_day:
            buy = build_outcome(action="BUY", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by)
            sell = build_outcome(action="SELL", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by)
            if buy.get("data_quality_status") == "OK" and sell.get("data_quality_status") == "OK":
                rows.append({"day": day, "idx": idx, "buy": buy, "sell": sell})
                n += 1
            idx += stride
    return rows


def _cal(nets: list[float]) -> dict[str, Any]:
    if not nets:
        return {"n": 0, "mean": None, "p_pos": None, "p05": None, "max_dd": None}
    m = sum(nets) / len(nets)
    eq = peak = 0.0
    dd = 0.0
    for x in nets:
        eq += x
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {
        "n": len(nets),
        "mean": m,
        "p_pos": sum(1 for x in nets if x > 0) / len(nets),
        "p05": sorted(nets)[max(0, int(0.05 * len(nets)))],
        "max_dd": dd,
    }


def run_stress(days: list[str]) -> dict[str, Any]:
    events = _event_outcomes(days)
    by_scenario: dict[str, dict[str, Any]] = {}
    for sid, sc in COST_SCENARIO_REGISTRY.items():
        buy_nets = []
        sell_nets = []
        for e in events:
            for side, oc in (("BUY", e["buy"]), ("SELL", e["sell"])):
                entry_spread = float(oc.get("entry_spread") or (float(oc["entry_ask"]) - float(oc["entry_bid"])))
                exit_spread = float(oc.get("exit_spread") or (float(oc["exit_ask"]) - float(oc["exit_bid"])))
                applied = apply_scenario_costs(
                    gross_pnl=float(oc["gross_pnl"]),
                    risk_amount=float(oc["risk_amount"]),
                    entry_spread=entry_spread,
                    exit_spread=exit_spread,
                    scenario=sc,
                )
                net = applied.get("net_r")
                if net is None:
                    continue
                (buy_nets if side == "BUY" else sell_nets).append(float(net))
        by_scenario[sid] = {
            "BUY": _cal(buy_nets),
            "SELL": _cal(sell_nets),
            "BOTH": _cal(buy_nets + sell_nets),
            "live_broker_truth": sc.get("live_broker_truth"),
            "unknown_components": [
                c
                for c, v in (
                    ("commission", sc.get("commission_usd_per_side")),
                    ("slippage", sc.get("slippage_usd_per_side")),
                )
                if v is None
            ],
        }

    # Extreme filter: bars where entry spread/ATR is high under observed path
    high_spread = []
    normal = []
    for e in events:
        for oc in (e["buy"], e["sell"]):
            atr = float(oc.get("risk_amount") or 0)
            sp = float(oc.get("entry_spread") or (float(oc["entry_ask"]) - float(oc["entry_bid"])))
            ratio = (sp / atr) if atr > 0 else None
            row = float(oc["net_r"]) if oc.get("net_r") is not None else None
            if row is None or ratio is None:
                continue
            if ratio > 0.05:
                high_spread.append(row)
            else:
                normal.append(row)

    out = {
        "n_events": len(events),
        "days_n": len(days),
        "by_scenario": by_scenario,
        "observed_regime_split": {
            "normal_spread_atr_le_0.05": _cal(normal),
            "elevated_spread_atr_gt_0.05": _cal(high_spread),
        },
        "gross_vs_net_note": (
            "OBSERVED_BIDASK_ONLY net_r equals path gross_r (spread embedded). "
            "Stress scenarios add labeled friction only; not claimed live costs."
        ),
        "holdout_excluded": True,
    }
    out["stress_sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "stress_sha256"})
    return out
