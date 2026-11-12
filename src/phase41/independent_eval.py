"""Independent reconstruction path — reloads disk and recomputes without primary trade objects."""

from __future__ import annotations

from typing import Any

from phase41.constants import HORIZON_BARS, TARGET_DATES
from phase41.data import load_day
from phase41.execution import simulate_trade
from phase41.features import build_feature_bundle
from phase41.signals import decide_h13c_frozen, decide_mr_frozen


def _reconstruct_from_disk(candidate_id: str, decide_fn) -> list[dict[str, Any]]:
    """Fresh load of every Phase40 day; rebuild features; re-simulate."""
    out: list[dict[str, Any]] = []
    for day in TARGET_DATES:
        # Independent reload — new load_day call, new feature bundle
        d = load_day(day)
        if not d["bars"]:
            continue
        feat = build_feature_bundle(list(d["bars"]), list(d["h1_bars"]))
        times = list(feat["feature_times"])
        ticks_by_bar = dict(d["ticks_by_bar"])
        for i, t in enumerate(times):
            if i + HORIZON_BARS >= len(times):
                continue
            action, reason = decide_fn(feat, t)
            if action not in {"BUY", "SELL"}:
                continue
            atr = feat["features"][t].get("atr_14")
            if not atr:
                out.append(
                    {
                        "candidate": candidate_id,
                        "day": day,
                        "signal_time": t,
                        "side": action,
                        "signal_reason": reason,
                        "status": "INSUFFICIENT_TICK_COVERAGE",
                        "net_r": None,
                        "entry_fill": None,
                        "exit_fill": None,
                        "exit_reason": None,
                    }
                )
                continue
            sim = simulate_trade(
                side=action,
                signal_idx=i,
                times=times,
                ticks_by_bar=ticks_by_bar,
                atr=float(atr),
                adverse_ambiguous=True,
            )
            out.append(
                {
                    "candidate": candidate_id,
                    "day": day,
                    "signal_time": t,
                    "side": action,
                    "signal_reason": reason,
                    "status": sim.get("status"),
                    "net_r": sim.get("net_r"),
                    "entry_fill": sim.get("entry_fill"),
                    "exit_fill": sim.get("exit_fill"),
                    "exit_reason": sim.get("exit_reason"),
                }
            )
    return out


def compare_independent(primary: dict[str, Any]) -> dict[str, Any]:
    results = {}
    for cid, decide in (("H13_C", decide_h13c_frozen), ("mean_reversion", decide_mr_frozen)):
        indep = _reconstruct_from_disk(cid, decide)
        prim = primary[cid]["trades"]
        pmap = {f"{t['day']}|{t['signal_time']}|{t['side']}": t for t in prim}
        imap = {f"{t['day']}|{t['signal_time']}|{t['side']}": t for t in indep}
        keys = sorted(set(pmap) | set(imap))
        matches = 0
        mismatches = []
        for k in keys:
            a, b = pmap.get(k), imap.get(k)
            if a is None or b is None:
                mismatches.append({"key": k, "reason": "missing_in_one_path"})
                continue
            ok = (
                a.get("status") == b.get("status")
                and a.get("exit_reason") == b.get("exit_reason")
                and a.get("entry_fill") == b.get("entry_fill")
                and a.get("exit_fill") == b.get("exit_fill")
                and (
                    (a.get("net_r") is None and b.get("net_r") is None)
                    or (
                        a.get("net_r") is not None
                        and b.get("net_r") is not None
                        and abs(float(a["net_r"]) - float(b["net_r"])) < 1e-12
                    )
                )
            )
            if ok:
                matches += 1
            else:
                mismatches.append(
                    {
                        "key": k,
                        "primary": {x: a.get(x) for x in ("status", "net_r", "entry_fill", "exit_fill", "exit_reason")},
                        "independent": {
                            x: b.get(x) for x in ("status", "net_r", "entry_fill", "exit_fill", "exit_reason")
                        },
                    }
                )
        results[cid] = {
            "n_primary": len(prim),
            "n_independent": len(indep),
            "n_keys": len(keys),
            "exact_matches": matches,
            "mismatches": mismatches[:50],
            "n_mismatches": len(mismatches),
            "ok": len(mismatches) == 0,
        }
    return {
        "ok": all(v["ok"] for v in results.values()),
        "by_candidate": results,
        "method": "independent disk reload + feature rebuild + re-simulate; does not reuse primary trade objects",
    }
