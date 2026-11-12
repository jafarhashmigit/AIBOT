"""Discovery screening and one-shot validation. No validation peeking during discovery."""

from __future__ import annotations

from typing import Any

from phase44.constants import (
    EFFECT_SIZE_MIN,
    MIN_DATES_WITH_EVENTS,
    MIN_EVENTS_DISCOVERY,
    MIN_EVENTS_VALIDATION,
    PURGE_BARS,
    SLIPPAGE_STRESS,
    SPREAD_WIDEN,
)
from phase44.data import load_ticks, ticks_by_m5_bar
from phase44.hypotheses import primary_hypotheses
from phase44.stats import date_block_bootstrap_vs_zero, group_by_day, leave_one_date_out, mean
from phase44.triggers import detect_events


def _purge(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) > 2 * PURGE_BARS:
        return rows[PURGE_BARS:-PURGE_BARS]
    return rows


def predictive_eval(hid: str, hyp: dict[str, Any], corpus: dict[str, list], dates: list[str], *, split: str) -> dict[str, Any]:
    h = int(hyp["horizon_bars"])
    key = f"ret_atr_h{h}"
    events = []
    for day in dates:
        rows = _purge(corpus.get(day) or [])
        idx = {r["time"]: r for r in rows}
        for e in detect_events(hid, rows):
            r = idx.get(e["time"])
            if not r or r.get(key) is None or e.get("side") in (None, 0):
                continue
            y = float(e["side"]) * float(r[key])
            events.append({"day": day, "time": e["time"], "side": e["side"], "y": y, "atr": e.get("atr")})
    cond_by = group_by_day([(e["day"], e["y"]) for e in events])
    boot = date_block_bootstrap_vs_zero(cond_by, seed=hash(hid) % 10000)
    lodo = leave_one_date_out(cond_by)
    ys = [e["y"] for e in events]
    acc = sum(1 for y in ys if y > 0) / len(ys) if ys else None
    by_date = {d: {"n": len(vs), "mean": mean(vs)} for d, vs in sorted(cond_by.items())}
    return {
        "hypothesis_id": hid,
        "split": split,
        "n_events": len(events),
        "n_dates": len(cond_by),
        "horizon": h,
        "effect": mean(ys),
        "directional_accuracy": acc,
        "bootstrap": boot,
        "lodo": lodo,
        "by_date": by_date,
        "events_sample": events[:15],
    }


def decision_eval(hid: str, hyp: dict[str, Any], corpus: dict[str, list], dates: list[str]) -> dict[str, Any]:
    """HISTORICAL_HYPOTHETICAL bid/ask path simulation."""
    horizon = int(hyp["horizon_bars"])
    trades = []
    for day in dates:
        rows = corpus.get(day) or []
        ticks_by = ticks_by_m5_bar(load_ticks(day))
        idx = {r["time"]: i for i, r in enumerate(rows)}
        for e in detect_events(hid, rows):
            if e.get("side") not in (-1, 1):
                continue
            i = idx.get(e["time"])
            if i is None or i + horizon >= len(rows):
                trades.append({**e, "status": "INSUFFICIENT_PATH", "net_r": None})
                continue
            path_bars = [rows[j]["time"] for j in range(i + 1, i + 1 + horizon)]
            if any(not ticks_by.get(b) for b in path_bars):
                trades.append({**e, "status": "INSUFFICIENT_TICK_COVERAGE", "net_r": None})
                continue
            entry_bar = path_bars[0]
            et = sorted(ticks_by[entry_bar], key=lambda t: t["epoch_ms"])
            atr = float(e.get("atr") or 0)
            if atr <= 0:
                trades.append({**e, "status": "NO_ATR", "net_r": None})
                continue
            side = e["side"]
            if side > 0:
                entry = float(et[0]["ask"])
                tp, sl = entry + 1.5 * atr, entry - 1.0 * atr
            else:
                entry = float(et[0]["bid"])
                tp, sl = entry - 1.5 * atr, entry + 1.0 * atr
            spread = float(et[0]["ask"]) - float(et[0]["bid"])
            path = []
            for b in path_bars:
                path.extend(sorted(ticks_by[b], key=lambda t: t["epoch_ms"]))
            entry_ms = et[0]["epoch_ms"]
            exit_px = reason = None
            for t in path:
                if t["epoch_ms"] < entry_ms:
                    continue
                bid, ask = float(t["bid"]), float(t["ask"])
                if side > 0:
                    hit_sl, hit_tp = bid <= sl, bid >= tp
                    if hit_sl and hit_tp:
                        exit_px, reason = bid, "FAIL"
                        break
                    if hit_sl:
                        exit_px, reason = bid, "FAIL"
                        break
                    if hit_tp:
                        exit_px, reason = bid, "PASS"
                        break
                else:
                    hit_sl, hit_tp = ask >= sl, ask <= tp
                    if hit_sl and hit_tp:
                        exit_px, reason = ask, "FAIL"
                        break
                    if hit_sl:
                        exit_px, reason = ask, "FAIL"
                        break
                    if hit_tp:
                        exit_px, reason = ask, "PASS"
                        break
            if exit_px is None:
                last = path[-1]
                exit_px = float(last["bid"] if side > 0 else last["ask"])
                reason = "TIMEOUT"
            pnl = (exit_px - entry) if side > 0 else (entry - exit_px)
            trades.append(
                {
                    **e,
                    "status": reason,
                    "entry": entry,
                    "exit": exit_px,
                    "entry_spread": spread,
                    "net_pnl": pnl,
                    "net_r": pnl / atr,
                    "experience_source": "HISTORICAL_HYPOTHETICAL",
                }
            )
    scored = [t for t in trades if t.get("net_r") is not None]
    # portfolio: non-overlapping — skip if prior trade still in horizon (by signal index order)
    rs = [float(t["net_r"]) for t in scored]
    scenarios = []
    for slip in SLIPPAGE_STRESS:
        for widen in SPREAD_WIDEN:
            if not scored:
                continue
            adj = []
            for t in scored:
                extra = 2 * slip + float(t.get("entry_spread") or 0) * (widen - 1.0)
                adj.append((float(t["net_pnl"]) - extra) / float(t["atr"]))
            scenarios.append(
                {
                    "slippage_per_side": slip,
                    "spread_widen": widen,
                    "mean_r": mean(adj),
                    "pct_pos": sum(1 for x in adj if x > 0) / len(adj),
                    "hypothetical": True,
                }
            )
    # drawdown
    eq = peak = max_dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        max_dd = min(max_dd, eq - peak)
    gp = sum(x for x in rs if x > 0)
    gl = abs(sum(x for x in rs if x <= 0))
    return {
        "n_signals": len(trades),
        "n_scored": len(scored),
        "mean_net_r": mean(rs),
        "win_rate": (sum(1 for x in rs if x > 0) / len(rs)) if rs else None,
        "profit_factor": (gp / gl) if gl > 0 else (None if gp == 0 else float("inf")),
        "max_dd_r": max_dd if rs else None,
        "scenarios": scenarios,
        "by_date": {
            d: {
                "n": len([t for t in scored if t["day"] == d]),
                "mean_r": mean([float(t["net_r"]) for t in scored if t["day"] == d]),
            }
            for d in dates
        },
        "experience_source": "HISTORICAL_HYPOTHETICAL",
    }


def screen_discovery(corpus: dict[str, list], dates: list[str]) -> dict[str, Any]:
    results = []
    rejected = []
    survivors = []
    for hyp in primary_hypotheses():
        hid = hyp["id"]
        pred = predictive_eval(hid, hyp, corpus, dates, split="discovery")
        reasons = []
        if pred["n_events"] < MIN_EVENTS_DISCOVERY:
            reasons.append(f"n={pred['n_events']}<{MIN_EVENTS_DISCOVERY}")
        if pred["n_dates"] < MIN_DATES_WITH_EVENTS:
            reasons.append(f"dates={pred['n_dates']}<{MIN_DATES_WITH_EVENTS}")
        if pred.get("effect") is None or pred["effect"] < EFFECT_SIZE_MIN:
            reasons.append(f"effect={pred.get('effect')}")
        boot = pred.get("bootstrap") or {}
        if not boot.get("bonferroni_excludes_zero"):
            reasons.append("bonferroni_ci_includes_zero")
        lodo = pred.get("lodo") or {}
        if lodo.get("ok") and not lodo.get("all_positive"):
            reasons.append("lodo_not_all_positive")

        predictive_pass = len(reasons) == 0
        decision = {"skipped": True, "reason": "predictive_failed"}
        decision_value = False
        if predictive_pass:
            decision = decision_eval(hid, hyp, corpus, dates)
            stress = next(
                (
                    s
                    for s in (decision.get("scenarios") or [])
                    if s.get("slippage_per_side") == 0.1 and s.get("spread_widen") == 1.5
                ),
                None,
            )
            if (decision.get("mean_net_r") or 0) > 0 and stress and (stress.get("mean_r") or 0) > 0:
                decision_value = True
            elif (decision.get("mean_net_r") or 0) > 0 and stress is None:
                decision_value = True
            else:
                reasons.append("no_decision_value_after_costs")
                # still predictive_pass but no decision value

        status = "REJECTED"
        if predictive_pass and decision_value:
            status = "SURVIVOR_PREDICTIVE_AND_DECISION"
            survivors.append(hid)
        elif predictive_pass:
            status = "PREDICTIVE_ONLY"
            survivors.append(hid)  # still freeze for validation of predictive claim

        row = {
            "hypothesis_id": hid,
            "family": hyp["family"],
            "status": status,
            "rejection_reasons": reasons if status == "REJECTED" else ([] if decision_value else reasons),
            "predictive_pass": predictive_pass,
            "decision_value": decision_value,
            "discovery_predictive": pred,
            "discovery_decision": decision,
        }
        results.append(row)
        if status == "REJECTED":
            rejected.append({"hypothesis_id": hid, "reasons": reasons})

    return {
        "split": "discovery",
        "dates": dates,
        "results": results,
        "rejected": rejected,
        "survivor_ids": survivors,
        "note": "Validation dates not used",
    }


def validate_frozen(corpus: dict[str, list], dates: list[str], survivor_ids: list[str]) -> dict[str, Any]:
    """One-shot validation on frozen survivors only."""
    by_id = {h["id"]: h for h in primary_hypotheses()}
    results = []
    for hid in survivor_ids:
        hyp = by_id[hid]
        pred = predictive_eval(hid, hyp, corpus, dates, split="validation")
        reasons = []
        if pred["n_events"] < MIN_EVENTS_VALIDATION:
            reasons.append(f"val_n={pred['n_events']}<{MIN_EVENTS_VALIDATION}")
        if pred["n_dates"] < MIN_DATES_WITH_EVENTS:
            reasons.append(f"val_dates={pred['n_dates']}<{MIN_DATES_WITH_EVENTS}")
        if pred.get("effect") is None or pred["effect"] < EFFECT_SIZE_MIN / 2:
            reasons.append(f"val_effect={pred.get('effect')}")
        boot = pred.get("bootstrap") or {}
        if not boot.get("bonferroni_excludes_zero"):
            reasons.append("val_bonferroni_includes_zero")
        if not (pred.get("lodo") or {}).get("all_positive", False):
            reasons.append("val_lodo_not_all_positive")

        decision = decision_eval(hid, hyp, corpus, dates)
        stress = next(
            (
                s
                for s in (decision.get("scenarios") or [])
                if s.get("slippage_per_side") == 0.1 and s.get("spread_widen") == 1.5
            ),
            None,
        )
        decision_value = (decision.get("mean_net_r") or 0) > 0 and (
            stress is None or (stress.get("mean_r") or 0) > 0
        )
        predictive_ok = len(reasons) == 0
        results.append(
            {
                "hypothesis_id": hid,
                "validation_predictive": pred,
                "validation_decision": decision,
                "predictive_confirmed": predictive_ok,
                "decision_confirmed": decision_value,
                "rejection_reasons": reasons,
            }
        )
    return {"split": "validation", "dates": dates, "results": results, "one_shot": True}
