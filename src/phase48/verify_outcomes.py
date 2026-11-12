"""Complete Phase46 11,211-row verification including WAIT."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from phase46.data import load_m5, load_ticks, ticks_by_m5_bar
from phase46.independent import recompute_directional
from phase48.constants import (
    ENGINEERING_DATES,
    EXPECTED_N,
    EXPECTED_PER_ACTION,
    FORBIDDEN_VALIDATION_DATES,
    PHASE46_CONTRACT,
    PHASE46_CONTRACT_SHA256_EXPECTED,
    PHASE46_OUTCOMES,
    canonical_json_sha256,
)


def load_outcomes(path: Path = PHASE46_OUTCOMES) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def verify_contract() -> dict[str, Any]:
    c = json.loads(PHASE46_CONTRACT.read_text(encoding="utf-8"))
    stored = c.get("contract_sha256")
    recomputed = canonical_json_sha256({k: v for k, v in c.items() if k != "contract_sha256"})
    return {
        "ok": stored == PHASE46_CONTRACT_SHA256_EXPECTED == recomputed,
        "expected": PHASE46_CONTRACT_SHA256_EXPECTED,
        "stored": stored,
        "recomputed": recomputed,
    }


def verify_wait_row(r: dict[str, Any]) -> list[str]:
    """WAIT is contractually deterministic zero incremental PnL — verify, do not assume silently."""
    errs = []
    if r.get("action") != "WAIT":
        return ["not_wait"]
    checks = {
        "gross_pnl": 0.0,
        "net_pnl": 0.0,
        "gross_r": 0.0,
        "net_r": 0.0,
        "mfe": 0.0,
        "mae": 0.0,
        "commission": 0.0,
        "slippage": 0.0,
        "exit_reason": "NO_POSITION",
    }
    for k, expected in checks.items():
        got = r.get(k)
        if got != expected:
            # float compare
            try:
                if abs(float(got) - float(expected)) > 1e-12:
                    errs.append(f"{k}={got}")
            except (TypeError, ValueError):
                if got != expected:
                    errs.append(f"{k}={got}")
    # scenario nets should also be zero
    for sid, sn in (r.get("scenario_nets") or {}).items():
        if sn.get("net_pnl") not in (0, 0.0) or (
            sn.get("net_r") not in (0, 0.0, None) and float(sn.get("net_r") or 0) != 0.0
        ):
            # net_r may be 0.0
            if sn.get("net_pnl") not in (0, 0.0):
                errs.append(f"scenario:{sid}:net_pnl")
            if sn.get("net_r") is not None and abs(float(sn["net_r"])) > 1e-12:
                errs.append(f"scenario:{sid}:net_r")
    if r.get("entry_timestamp") is not None or r.get("exit_timestamp") is not None:
        # WAIT has no fills — timestamps should be None per Phase46 contract
        errs.append("unexpected_fill_timestamps")
    return errs


def full_verify_11211(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows if rows is not None else load_outcomes()
    contract = verify_contract()
    counts = Counter(r.get("action") for r in rows)
    days = sorted({str(r.get("day")) for r in rows})
    forbidden = sorted(set(days) & FORBIDDEN_VALIDATION_DATES)
    keys = {(r.get("day"), r.get("decision_bar"), r.get("action")) for r in rows}
    duplicates = len(rows) - len(keys)

    # Phase47 discrepancy explanation
    phase47_note = {
        "phase47_reported_total": EXPECTED_N,
        "phase47_reported_independent_directional": EXPECTED_PER_ACTION * 2,
        "phase47_remaining": EXPECTED_PER_ACTION,
        "explanation": (
            "Phase47 preflight independently recomputed BUY+SELL only (7,474). "
            "The remaining 3,737 WAIT rows were structurally checked for zero PnL in structural_audit "
            "but were NOT passed through tick-path independent recomputation — because WAIT has no "
            "bid/ask path by contract. Phase48 verifies every WAIT row explicitly against the "
            "deterministic zero-PnL contract."
        ),
    }

    wait_checked = 0
    wait_failures: list[dict[str, Any]] = []
    for r in rows:
        if r.get("action") != "WAIT":
            continue
        wait_checked += 1
        errs = verify_wait_row(r)
        if errs:
            wait_failures.append({"day": r.get("day"), "decision_bar": r.get("decision_bar"), "errs": errs})

    # Directional independent recompute (all BUY/SELL)
    directional = [r for r in rows if r.get("action") in ("BUY", "SELL")]
    mismatches: list[dict[str, Any]] = []
    checked_dir = 0
    skipped: list[dict[str, Any]] = []

    by_day: dict[str, list] = {}
    for r in directional:
        by_day.setdefault(str(r["day"]), []).append(r)

    for day, day_rows in sorted(by_day.items()):
        if day not in ENGINEERING_DATES:
            skipped.append({"day": day, "reason": "not_in_engineering_dates", "n": len(day_rows)})
            continue
        m5 = load_m5(day)
        by_bar = ticks_by_m5_bar(load_ticks(day))
        idx_map = {str(b["timestamp_utc"]): i for i, b in enumerate(m5)}
        for r in day_rows:
            checked_dir += 1
            idx = idx_map.get(str(r["decision_bar"]))
            if idx is None:
                mismatches.append({"key": f"{day}|{r['decision_bar']}|{r['action']}", "reason": "missing_bar"})
                continue
            rec = recompute_directional(
                action=str(r["action"]),
                day=day,
                decision_idx=idx,
                m5=m5,
                ticks_by_bar=by_bar,
            )
            if rec.get("data_quality_status") != "OK":
                mismatches.append(
                    {
                        "key": f"{day}|{r['decision_bar']}|{r['action']}",
                        "reason": "independent_not_ok",
                        "status": rec.get("data_quality_status"),
                    }
                )
                continue
            diffs = {}
            for f in ("gross_pnl", "net_pnl", "net_r", "gross_r", "entry_bid", "entry_ask", "exit_bid", "exit_ask"):
                a, b = r.get(f), rec.get(f)
                if a is None or b is None:
                    if a != b:
                        diffs[f] = {"primary": a, "independent": b}
                elif abs(float(a) - float(b)) > 1e-8:
                    diffs[f] = {"primary": a, "independent": b}
            if r.get("outcome_sha256") != rec.get("outcome_sha256"):
                diffs["outcome_sha256"] = {"primary": r.get("outcome_sha256"), "independent": rec.get("outcome_sha256")}
            # no double-count: OBSERVED net == gross
            sn = (r.get("scenario_nets") or {}).get("OBSERVED_BIDASK_ONLY") or {}
            if sn and abs(float(r["gross_pnl"]) - float(sn["net_pnl"])) > 1e-9:
                diffs["double_count_spread"] = {"gross": r["gross_pnl"], "observed_net": sn["net_pnl"]}
            if diffs:
                mismatches.append({"key": f"{day}|{r['decision_bar']}|{r['action']}", "diffs": diffs})

    # Fill convention spot-check counts
    buy_fill_ok = sum(
        1
        for r in rows
        if r["action"] == "BUY" and r.get("entry_fill") == r.get("entry_ask") and r.get("exit_fill") == r.get("exit_bid")
    )
    sell_fill_ok = sum(
        1
        for r in rows
        if r["action"] == "SELL" and r.get("entry_fill") == r.get("entry_bid") and r.get("exit_fill") == r.get("exit_ask")
    )

    total_verified = checked_dir + wait_checked
    ok = (
        contract["ok"]
        and len(rows) == EXPECTED_N
        and counts.get("BUY") == EXPECTED_PER_ACTION
        and counts.get("SELL") == EXPECTED_PER_ACTION
        and counts.get("WAIT") == EXPECTED_PER_ACTION
        and not forbidden
        and duplicates == 0
        and len(mismatches) == 0
        and len(wait_failures) == 0
        and checked_dir == EXPECTED_PER_ACTION * 2
        and wait_checked == EXPECTED_PER_ACTION
        and total_verified == EXPECTED_N
    )

    return {
        "ok": ok,
        "contract": contract,
        "n_rows": len(rows),
        "action_counts": dict(counts),
        "days": days,
        "forbidden_hits": forbidden,
        "duplicates": duplicates,
        "phase47_7474_vs_11211": phase47_note,
        "directional": {
            "checked": checked_dir,
            "mismatches": len(mismatches),
            "mismatch_sample": mismatches[:15],
            "skipped": skipped,
        },
        "wait": {
            "checked": wait_checked,
            "failures": len(wait_failures),
            "failure_sample": wait_failures[:15],
            "method": "deterministic_zero_pnl_contract_verification",
            "note": "WAIT has no tick path; verification is contractual field equality, not bid/ask replay",
        },
        "fill_conventions": {
            "buy_ask_entry_bid_exit_ok": buy_fill_ok,
            "sell_bid_entry_ask_exit_ok": sell_fill_ok,
            "expected_each": EXPECTED_PER_ACTION,
        },
        "total_records_accounted": total_verified,
        "excluded_or_skipped": skipped,
        "every_record_explained": total_verified == len(rows) and not skipped,
    }
