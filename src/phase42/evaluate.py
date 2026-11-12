"""Discovery/validation evaluation — predictive first, then decision value."""

from __future__ import annotations

from typing import Any

from phase42.constants import (
    DISCOVERY_DATES,
    EFFECT_SIZE_MIN,
    HORIZONS,
    MIN_DATES_WITH_EVENTS,
    MIN_EVENTS_DISCOVERY,
    MIN_EVENTS_VALIDATION,
    PURGE_BARS,
    SLIPPAGE_STRESS,
    SPREAD_WIDEN,
    VALIDATION_DATES,
)
from phase42.data import list_days, load_h1, load_m5, load_ticks_hours, ticks_by_m5_bar
from phase42.features import build_feature_rows
from phase42.hypotheses import frozen_hypothesis_registry
from phase42.labels import attach_forward_labels
from phase42.stats import date_block_bootstrap_diff, group_by_day, leave_one_date_out_effect, mean
from phase42.triggers import detect_events


def _build_day(day: str, *, need_ticks: bool) -> list[dict[str, Any]]:
    bars = load_m5(day)
    h1 = load_h1(day)
    ticks_by = None
    if need_ticks:
        ticks_by = ticks_by_m5_bar(load_ticks_hours(day))
    rows = build_feature_rows(bars, h1, ticks_by)
    return attach_forward_labels(rows)


def build_corpus(*, need_ticks: bool = True) -> dict[str, list[dict[str, Any]]]:
    return {day: _build_day(day, need_ticks=need_ticks) for day in list_days()}


def _index_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["time"]: r for r in rows}


def _unconditional_metric(rows: list[dict[str, Any]], key: str) -> list[tuple[str, float]]:
    out = []
    for r in rows:
        v = r.get(key)
        if v is not None:
            out.append((r["day"], float(v)))
    return out


def _predictive_for_hypothesis(
    hid: str,
    hyp: dict[str, Any],
    corpus: dict[str, list[dict[str, Any]]],
    dates: list[str],
    *,
    split: str,
) -> dict[str, Any]:
    horizon = int(hyp["horizon_bars"])
    # map horizon to available keys
    hkey = horizon if horizon in HORIZONS else min(HORIZONS, key=lambda x: abs(x - horizon))
    unsigned = hyp.get("decision_side") is None
    metric_key = f"abs_ret_atr_h{hkey}" if unsigned else f"ret_atr_h{hkey}"

    events = []
    all_rows = []
    for day in dates:
        rows = corpus.get(day) or []
        # purge near day edges lightly
        if len(rows) > 2 * PURGE_BARS:
            rows_use = rows[PURGE_BARS : -PURGE_BARS]
        else:
            rows_use = rows
        all_rows.extend(rows_use)
        idx = _index_rows(rows)
        for e in detect_events(hid, rows_use):
            r = idx.get(e["time"])
            if not r:
                continue
            if unsigned:
                y = r.get(metric_key)
                if y is None:
                    continue
                events.append({"day": day, "time": e["time"], "y": float(y), "side": None})
            else:
                y = r.get(f"ret_atr_h{hkey}")
                if y is None or e.get("side") in (None, 0):
                    continue
                # signed outcome in predicted direction
                events.append({"day": day, "time": e["time"], "y": float(e["side"]) * float(y), "side": e["side"]})

    uncond_pairs = _unconditional_metric(all_rows, metric_key if unsigned else f"ret_atr_h{hkey}")
    # for directional, unconditional signed toward random is ~0 using raw ret; use abs? 
    # Better: unconditional = mean of |ret| * 0 for signed baseline = 0, compare conditional signed mean to 0 AND to mean(|ret|)
    if not unsigned:
        # baseline: random side → expected signed ret ~ 0; also compare to mean abs
        uncond_y = [(d, 0.0) for d, _ in uncond_pairs]  # degenerate — use raw abs as cost of being wrong
        # Use unconditional mean of side-randomized: actually compare conditional to 0 via bootstrap of conditional only
        cond_by = group_by_day([(e["day"], e["y"]) for e in events])
        # fabricate uncond as zeros per day with same counts for diff vs 0
        uncond_by = {d: [0.0] * len(vs) for d, vs in cond_by.items()}
        boot = date_block_bootstrap_diff(cond_by, uncond_by, seed=hash(hid) % 10_000)
        lodo = leave_one_date_out_effect(cond_by, uncond_by)
        cond_vals = [e["y"] for e in events]
        # also accuracy
        acc = sum(1 for e in events if e["y"] > 0) / len(events) if events else None
        # MFE/MAE alignment
        mfe_key = f"mfe_atr_h{hkey}"
        mae_key = f"mae_atr_h{hkey}"
        fav = []
        for e in events:
            r = next((x for x in (corpus.get(e["day"]) or []) if x["time"] == e["time"]), None)
            if not r:
                continue
            mfe, mae = r.get(mfe_key), r.get(mae_key)
            if mfe is None or mae is None or e["side"] is None:
                continue
            # rotate to side
            if e["side"] > 0:
                fav.append(1.0 if mfe >= abs(mae) else 0.0)
            else:
                # for short, favorable is negative move → use -mae as mfe
                fav.append(1.0 if abs(mae) >= mfe else 0.0)
        return {
            "hypothesis_id": hid,
            "split": split,
            "n_events": len(events),
            "n_dates": len({e["day"] for e in events}),
            "metric": "signed_ret_atr_aligned",
            "horizon": hkey,
            "conditional_mean": mean(cond_vals),
            "unconditional_mean": 0.0,
            "effect": mean(cond_vals),
            "directional_accuracy": acc,
            "fav_ge_adv_rate": mean(fav) if fav else None,
            "bootstrap": boot,
            "lodo": lodo,
            "events_sample": events[:20],
        }

    # unsigned: conditional abs_ret vs unconditional abs_ret
    # For H42_E (compression) success is LOWER abs ret; for H42_A higher
    cond_by = group_by_day([(e["day"], e["y"]) for e in events])
    uncond_by = group_by_day(uncond_pairs)
    boot = date_block_bootstrap_diff(cond_by, uncond_by, seed=hash(hid) % 10_000)
    lodo = leave_one_date_out_effect(cond_by, uncond_by)
    cond_vals = [e["y"] for e in events]
    unc_vals = [v for _, v in uncond_pairs]
    effect = (mean(cond_vals) or 0) - (mean(unc_vals) or 0)
    return {
        "hypothesis_id": hid,
        "split": split,
        "n_events": len(events),
        "n_dates": len({e["day"] for e in events}),
        "metric": metric_key,
        "horizon": hkey,
        "conditional_mean": mean(cond_vals),
        "unconditional_mean": mean(unc_vals),
        "effect": effect,
        "bootstrap": boot,
        "lodo": lodo,
        "events_sample": events[:20],
        "unsigned_direction": "higher_abs" if hid.endswith("EXPAND") else "lower_abs",
    }


def _decision_eval(
    hid: str,
    hyp: dict[str, Any],
    corpus: dict[str, list[dict[str, Any]]],
    dates: list[str],
    ticks_corpus: dict[str, dict[str, list]],
) -> dict[str, Any]:
    """Simple next-open bid/ask H-horizon exit (timeout at horizon) — HISTORICAL_HYPOTHETICAL only."""
    if hyp.get("decision_side") is None:
        return {"skipped": True, "reason": "unsigned_hypothesis_no_trade_decision"}
    horizon = int(hyp["horizon_bars"])
    trades = []
    for day in dates:
        rows = corpus.get(day) or []
        ticks_by = ticks_corpus.get(day) or {}
        idx = {r["time"]: i for i, r in enumerate(rows)}
        for e in detect_events(hid, rows):
            if e.get("side") in (None, 0):
                continue
            i = idx.get(e["time"])
            if i is None or i + 1 + horizon - 1 >= len(rows):
                trades.append({**e, "status": "INSUFFICIENT_PATH", "net_r": None})
                continue
            entry_bar = rows[i + 1]["time"]
            path_bars = [rows[j]["time"] for j in range(i + 1, i + 1 + horizon)]
            if any(not ticks_by.get(b) for b in path_bars):
                trades.append({**e, "status": "INSUFFICIENT_TICK_COVERAGE", "net_r": None})
                continue
            entry_ticks = sorted(ticks_by[entry_bar], key=lambda t: t["epoch_ms"])
            side = e["side"]
            atr = float(e["atr"] or rows[i]["atr_14"] or 0)
            if atr <= 0:
                trades.append({**e, "status": "NO_ATR", "net_r": None})
                continue
            if side > 0:
                entry = float(entry_ticks[0]["ask"])
                tp, sl = entry + 1.5 * atr, entry - 1.0 * atr
            else:
                entry = float(entry_ticks[0]["bid"])
                tp, sl = entry - 1.5 * atr, entry + 1.0 * atr
            entry_spread = float(entry_ticks[0]["ask"]) - float(entry_ticks[0]["bid"])
            path = []
            for b in path_bars:
                path.extend(sorted(ticks_by[b], key=lambda t: t["epoch_ms"]))
            entry_ms = entry_ticks[0]["epoch_ms"]
            exit_px = None
            reason = None
            for t in path:
                if t["epoch_ms"] < entry_ms:
                    continue
                bid, ask = float(t["bid"]), float(t["ask"])
                if side > 0:
                    if bid <= sl and bid >= tp:
                        exit_px, reason = bid, "FAIL"  # adverse ambiguity
                        break
                    if bid <= sl:
                        exit_px, reason = bid, "FAIL"
                        break
                    if bid >= tp:
                        exit_px, reason = bid, "PASS"
                        break
                else:
                    if ask >= sl and ask <= tp:
                        exit_px, reason = ask, "FAIL"
                        break
                    if ask >= sl:
                        exit_px, reason = ask, "FAIL"
                        break
                    if ask <= tp:
                        exit_px, reason = ask, "PASS"
                        break
            if exit_px is None:
                last = path[-1]
                exit_px = float(last["bid"] if side > 0 else last["ask"])
                reason = "TIMEOUT"
            pnl = (exit_px - entry) if side > 0 else (entry - exit_px)
            net_r = pnl / atr
            trades.append(
                {
                    **e,
                    "status": reason,
                    "entry": entry,
                    "exit": exit_px,
                    "entry_spread": entry_spread,
                    "net_pnl": pnl,
                    "net_r": net_r,
                    "experience_source": "HISTORICAL_HYPOTHETICAL",
                }
            )

    scored = [t for t in trades if t.get("net_r") is not None]
    scenarios = []
    for slip in SLIPPAGE_STRESS:
        for widen in SPREAD_WIDEN:
            if not scored:
                continue
            rs = []
            for t in scored:
                extra = 2 * slip + (float(t.get("entry_spread") or 0) * (widen - 1.0))
                rs.append((float(t["net_pnl"]) - extra) / float(t["atr"]))
            scenarios.append(
                {
                    "slippage_per_side": slip,
                    "spread_widen": widen,
                    "mean_r": mean(rs),
                    "pct_pos": sum(1 for x in rs if x > 0) / len(rs),
                    "hypothetical": True,
                }
            )
    return {
        "skipped": False,
        "n_signals": len(trades),
        "n_scored": len(scored),
        "mean_net_r": mean([float(t["net_r"]) for t in scored]),
        "win_rate": (sum(1 for t in scored if float(t["net_r"]) > 0) / len(scored)) if scored else None,
        "scenarios": scenarios,
        "experience_source": "HISTORICAL_HYPOTHETICAL",
        "note": "Counterfactual historical fills; not AGENT_SHADOW",
    }


def evaluate_all(corpus: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    registry = frozen_hypothesis_registry()
    corpus = corpus or build_corpus(need_ticks=True)
    ticks_corpus = {day: ticks_by_m5_bar(load_ticks_hours(day)) for day in list_days()}

    results = []
    rejected = []
    for hyp in registry["hypotheses"]:
        hid = hyp["id"]
        disc = _predictive_for_hypothesis(hid, hyp, corpus, DISCOVERY_DATES, split="discovery")
        val = _predictive_for_hypothesis(hid, hyp, corpus, VALIDATION_DATES, split="validation")

        # gates
        reasons = []
        unsigned = hyp.get("decision_side") is None
        # effect sign expectation
        if unsigned and hyp["id"].endswith("SLOWDOWN"):
            want_positive_effect = False  # lower abs than uncond → effect negative is success
        else:
            want_positive_effect = True

        if disc["n_events"] < MIN_EVENTS_DISCOVERY:
            reasons.append(f"discovery_n={disc['n_events']}<{MIN_EVENTS_DISCOVERY}")
        if disc["n_dates"] < MIN_DATES_WITH_EVENTS:
            reasons.append(f"discovery_dates={disc['n_dates']}<{MIN_DATES_WITH_EVENTS}")
        if val["n_events"] < MIN_EVENTS_VALIDATION:
            reasons.append(f"validation_n={val['n_events']}<{MIN_EVENTS_VALIDATION}")
        if val["n_dates"] < MIN_DATES_WITH_EVENTS:
            reasons.append(f"validation_dates={val['n_dates']}<{MIN_DATES_WITH_EVENTS}")

        eff_d, eff_v = disc.get("effect"), val.get("effect")
        if want_positive_effect:
            if eff_d is None or eff_d < EFFECT_SIZE_MIN:
                reasons.append(f"discovery_effect={eff_d}")
            if eff_v is None or eff_v < EFFECT_SIZE_MIN / 2:
                reasons.append(f"validation_effect={eff_v}")
        else:
            if eff_d is None or eff_d > -EFFECT_SIZE_MIN:
                reasons.append(f"discovery_effect_not_lower={eff_d}")
            if eff_v is None or eff_v > -EFFECT_SIZE_MIN / 2:
                reasons.append(f"validation_effect_not_lower={eff_v}")

        boot_ok = bool((val.get("bootstrap") or {}).get("bonferroni_excludes_zero"))
        if not boot_ok:
            reasons.append("validation_bonferroni_ci_includes_zero")

        # chronological: discovery and validation same sign effect
        if eff_d is not None and eff_v is not None and (eff_d > 0) != (eff_v > 0) and want_positive_effect:
            reasons.append("discovery_validation_sign_flip")
        if (not want_positive_effect) and eff_d is not None and eff_v is not None and (eff_d < 0) != (eff_v < 0):
            reasons.append("discovery_validation_sign_flip")

        predictive_pass = len(reasons) == 0
        decision = {"skipped": True, "reason": "predictive_failed"}
        if predictive_pass:
            decision = _decision_eval(hid, hyp, corpus, VALIDATION_DATES, ticks_corpus)

        decision_value = False
        if not decision.get("skipped") and (decision.get("mean_net_r") or 0) > 0:
            # require stress scenario slip 0.1 widen 1.5 still >=0 if present
            stress = next(
                (
                    s
                    for s in (decision.get("scenarios") or [])
                    if s.get("slippage_per_side") == 0.1 and s.get("spread_widen") == 1.5
                ),
                None,
            )
            if stress and (stress.get("mean_r") or 0) > 0:
                decision_value = True
            elif stress is None and (decision.get("mean_net_r") or 0) > 0:
                decision_value = True

        status = "PREDICTIVE_PASS" if predictive_pass else "REJECTED"
        if predictive_pass and hyp.get("decision_side") is None:
            status = "PREDICTIVE_UNSIGNED"
        if predictive_pass and decision_value:
            status = "PREDICTIVE_AND_DECISION"

        row = {
            "hypothesis_id": hid,
            "family": hyp["family"],
            "status": status,
            "rejection_reasons": reasons,
            "discovery": disc,
            "validation": val,
            "decision_validation": decision,
            "decision_value": decision_value,
            "predictive_pass": predictive_pass,
        }
        results.append(row)
        if not predictive_pass:
            rejected.append({"hypothesis_id": hid, "family": hyp["family"], "reasons": reasons})

    return {
        "registry_n": registry["n_hypotheses"],
        "families_n": registry["n_families"],
        "discovery_dates": DISCOVERY_DATES,
        "validation_dates": VALIDATION_DATES,
        "results": results,
        "rejected": rejected,
        "caveat": (
            "All Phase40 dates were previously examined in Phases 38–41. "
            "Validation here is chronological holdout within that set — NOT independent replication."
        ),
    }
