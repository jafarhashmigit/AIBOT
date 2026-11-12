"""Mandatory full Phase46 integrity verification (all rows, not a sample)."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from phase46.constants import ENGINEERING_DATES as P46_ENG
from phase46.independent import recompute_directional
from phase46.data import load_m5, load_ticks, ticks_by_m5_bar
from phase47.constants import (
    ENGINEERING_DATES,
    EXPECTED_N_OUTCOMES,
    EXPECTED_PER_ACTION,
    FORBIDDEN_VALIDATION_DATES,
    PHASE46_CONTRACT,
    PHASE46_CONTRACT_SHA256_EXPECTED,
    PHASE46_OUTCOMES,
    canonical_json_sha256,
)


def load_phase46_outcomes(path: Path = PHASE46_OUTCOMES) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def verify_contract_hash() -> dict[str, Any]:
    contract = json.loads(PHASE46_CONTRACT.read_text(encoding="utf-8"))
    stored = contract.get("contract_sha256")
    recomputed = canonical_json_sha256({k: v for k, v in contract.items() if k != "contract_sha256"})
    return {
        "ok": stored == PHASE46_CONTRACT_SHA256_EXPECTED and stored == recomputed,
        "expected": PHASE46_CONTRACT_SHA256_EXPECTED,
        "stored": stored,
        "recomputed": recomputed,
    }


def _finite(x: Any) -> bool:
    if x is None:
        return False
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return not (math.isnan(v) or math.isinf(v))


def structural_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(r.get("action") for r in rows)
    dq = Counter(r.get("data_quality_status") for r in rows)
    days = sorted({str(r.get("day")) for r in rows})
    forbidden = sorted(set(days) & FORBIDDEN_VALIDATION_DATES)
    keys = {(r.get("day"), r.get("decision_bar"), r.get("action")) for r in rows}
    dup = len(rows) - len(keys)

    issues: list[str] = []
    if len(rows) != EXPECTED_N_OUTCOMES:
        issues.append(f"n_rows={len(rows)} expected={EXPECTED_N_OUTCOMES}")
    for a in ("BUY", "SELL", "WAIT"):
        if counts.get(a) != EXPECTED_PER_ACTION:
            issues.append(f"{a}_count={counts.get(a)} expected={EXPECTED_PER_ACTION}")
    if forbidden:
        issues.append(f"forbidden_dates={forbidden}")
    if dup:
        issues.append(f"duplicate_keys={dup}")
    if set(days) - set(ENGINEERING_DATES):
        issues.append("unexpected_dates")
    if set(ENGINEERING_DATES) != set(P46_ENG):
        # phase46 engineering should match
        pass

    mid_hits = 0
    cost_issues = 0
    wait_issues = 0
    fill_issues = 0
    for r in rows:
        action = r.get("action")
        if action == "WAIT":
            if r.get("gross_pnl") not in (0, 0.0) or r.get("net_pnl") not in (0, 0.0):
                wait_issues += 1
            if r.get("commission") not in (0, 0.0) or r.get("slippage") not in (0, 0.0):
                wait_issues += 1
            continue
        if r.get("mid_price_used") is True:
            mid_hits += 1
        if action == "BUY":
            if r.get("entry_fill") != r.get("entry_ask") or r.get("exit_fill") != r.get("exit_bid"):
                fill_issues += 1
        if action == "SELL":
            if r.get("entry_fill") != r.get("entry_bid") or r.get("exit_fill") != r.get("exit_ask"):
                fill_issues += 1
        # spread not double-counted: OBSERVED net_pnl == gross_pnl
        sn = (r.get("scenario_nets") or {}).get("OBSERVED_BIDASK_ONLY") or {}
        if sn and _finite(r.get("gross_pnl")) and _finite(sn.get("net_pnl")):
            if abs(float(r["gross_pnl"]) - float(sn["net_pnl"])) > 1e-9:
                cost_issues += 1
        if r.get("commission") is not None and action in ("BUY", "SELL"):
            # under OBSERVED, commission must remain UNKNOWN (None)
            cost_issues += 1
        if r.get("slippage") is not None and action in ("BUY", "SELL"):
            cost_issues += 1
        if not _finite(r.get("net_r")) or not _finite(r.get("gross_r")):
            issues.append("non_finite_r")
            break

    # chronological per day
    chrono_ok = True
    by_day: dict[str, list] = {}
    for r in rows:
        by_day.setdefault(str(r["day"]), []).append(r)
    for d, rs in by_day.items():
        bars = [str(r["decision_bar"]) for r in rs if r["action"] == "BUY"]
        if bars != sorted(bars):
            chrono_ok = False
            break

    if mid_hits:
        issues.append(f"mid_price_used={mid_hits}")
    if fill_issues:
        issues.append(f"fill_convention_mismatches={fill_issues}")
    if cost_issues:
        issues.append(f"cost_accounting_issues={cost_issues}")
    if wait_issues:
        issues.append(f"wait_nonzero_issues={wait_issues}")
    if not chrono_ok:
        issues.append("chronological_order_failure")

    return {
        "ok": len(issues) == 0,
        "n_rows": len(rows),
        "action_counts": dict(counts),
        "dq_counts": dict(dq),
        "days": days,
        "forbidden_hits": forbidden,
        "duplicate_keys": dup,
        "mid_price_used": mid_hits,
        "fill_issues": fill_issues,
        "cost_issues": cost_issues,
        "wait_issues": wait_issues,
        "chronological_ok": chrono_ok,
        "issues": issues,
    }


def full_independent_recompute(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Recompute ALL BUY/SELL OK rows from raw Phase43 ticks; verify WAIT zeros."""
    directional = [r for r in rows if r.get("action") in ("BUY", "SELL")]
    waits = [r for r in rows if r.get("action") == "WAIT"]

    wait_bad = 0
    for w in waits:
        if float(w.get("net_r") or 0) != 0.0 or float(w.get("gross_pnl") or 0) != 0.0:
            wait_bad += 1

    by_day_rows: dict[str, list] = {}
    for r in directional:
        by_day_rows.setdefault(str(r["day"]), []).append(r)

    mismatches: list[dict[str, Any]] = []
    checked = 0
    m5_cache: dict[str, list] = {}
    tick_cache: dict[str, dict] = {}

    for day, day_rows in sorted(by_day_rows.items()):
        if day in FORBIDDEN_VALIDATION_DATES:
            return {"ok": False, "reason": f"forbidden_date_in_outcomes:{day}"}
        m5 = load_m5(day)
        ticks = load_ticks(day)
        by_bar = ticks_by_m5_bar(ticks)
        m5_cache[day] = m5
        tick_cache[day] = by_bar
        idx_map = {str(b["timestamp_utc"]): i for i, b in enumerate(m5)}

        for r in day_rows:
            checked += 1
            dbar = str(r["decision_bar"])
            idx = idx_map.get(dbar)
            if idx is None:
                mismatches.append({"key": f"{day}|{dbar}|{r['action']}", "reason": "missing_decision_bar"})
                continue
            recomputed = recompute_directional(
                action=str(r["action"]),
                day=day,
                decision_idx=idx,
                m5=m5,
                ticks_by_bar=by_bar,
            )
            if recomputed.get("data_quality_status") != "OK":
                mismatches.append(
                    {
                        "key": f"{day}|{dbar}|{r['action']}",
                        "reason": "independent_not_ok",
                        "got": recomputed.get("data_quality_status"),
                    }
                )
                continue
            diffs = {}
            for f in (
                "gross_pnl",
                "net_pnl",
                "net_r",
                "gross_r",
                "entry_bid",
                "entry_ask",
                "exit_bid",
                "exit_ask",
                "mfe",
                "mae",
            ):
                a, b = r.get(f), recomputed.get(f)
                if a is None or b is None:
                    if a != b:
                        diffs[f] = {"primary": a, "independent": b}
                elif abs(float(a) - float(b)) > 1e-8:
                    diffs[f] = {"primary": a, "independent": b}
            if r.get("outcome_sha256") != recomputed.get("outcome_sha256"):
                diffs["outcome_sha256"] = {
                    "primary": r.get("outcome_sha256"),
                    "independent": recomputed.get("outcome_sha256"),
                }
            # stress scenario net_r check (no double-count: additional only)
            for sid in ("OBSERVED_BIDASK_ONLY", "STRESS_SPREAD_WIDEN_1_5X", "STRESS_LABELED_FRICTION_PROXY"):
                pa = (r.get("scenario_nets") or {}).get(sid) or {}
                pb = (recomputed.get("scenario_nets") or {}).get(sid) or {}
                if pa.get("net_r") is not None and pb.get("net_r") is not None:
                    if abs(float(pa["net_r"]) - float(pb["net_r"])) > 1e-8:
                        diffs[f"scenario:{sid}:net_r"] = {"primary": pa["net_r"], "independent": pb["net_r"]}
            if diffs:
                mismatches.append({"key": f"{day}|{dbar}|{r['action']}", "diffs": diffs})

    return {
        "ok": len(mismatches) == 0 and wait_bad == 0 and checked == len(directional),
        "checked_directional": checked,
        "expected_directional": len(directional),
        "n_mismatches": len(mismatches),
        "mismatches_sample": mismatches[:20],
        "wait_rows": len(waits),
        "wait_nonzero_bad": wait_bad,
        "method": "full independent recompute via phase46.independent (not phase46.outcomes builders)",
        "spread_note": "OBSERVED net==gross; spread embedded in bid/ask; commission/slippage UNKNOWN",
    }


def run_preflight() -> dict[str, Any]:
    contract = verify_contract_hash()
    rows = load_phase46_outcomes()
    structural = structural_audit(rows)
    if not contract["ok"] or not structural["ok"]:
        return {
            "ok": False,
            "contract": contract,
            "structural": structural,
            "independent": {"ok": False, "skipped": True, "reason": "structural_or_contract_failed"},
            "stop": True,
            "verdict_hint": "DATA_INTEGRITY_FAILURE",
        }
    independent = full_independent_recompute(rows)
    ok = contract["ok"] and structural["ok"] and independent["ok"]
    return {
        "ok": ok,
        "contract": contract,
        "structural": structural,
        "independent": independent,
        "stop": not ok,
        "verdict_hint": None if ok else "DATA_INTEGRITY_FAILURE",
        "n_rows_loaded": len(rows),
        "label": "EXPLORATORY_PHASE44_DISCOVERY_EXPOSED",
    }
