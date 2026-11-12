"""Independent verification of selection, overlap, and outcome fills."""

from __future__ import annotations

from typing import Any

from phase49.constants import FORBIDDEN_VALIDATION_DATES, HORIZON_BARS, canonical_json_sha256
from phase49.outcomes import build_outcome
from phase49.data import load_m5, load_ticks, ticks_by_m5_bar


def verify_selection(selection: dict[str, Any]) -> dict[str, Any]:
    body = {k: v for k, v in selection.items() if k != "selection_sha256"}
    recomputed = canonical_json_sha256(body)
    forbidden_hit = sorted(set(selection.get("selected_dates") or []) & FORBIDDEN_VALIDATION_DATES)
    return {
        "ok": recomputed == selection.get("selection_sha256") and not forbidden_hit,
        "recomputed_sha256": recomputed,
        "stored_sha256": selection.get("selection_sha256"),
        "forbidden_hits": forbidden_hit,
    }


def verify_events_sample(events: list[dict[str, Any]], max_n: int = 40) -> dict[str, Any]:
    mismatches = []
    checked = 0
    by_day: dict[str, list] = {}
    for e in events:
        by_day.setdefault(e["day"], []).append(e)

    for day, evs in list(by_day.items())[:8]:
        m5 = load_m5(day)
        by_bar = ticks_by_m5_bar(load_ticks(day))
        for e in evs[:5]:
            for action in ("BUY", "SELL"):
                checked += 1
                rec = build_outcome(
                    action=action,
                    day=day,
                    decision_idx=int(e["decision_idx"]),
                    m5=m5,
                    ticks_by_bar=by_bar,
                )
                primary = e["buy"] if action == "BUY" else e["sell"]
                if rec.get("net_r") is None or primary.get("net_r") is None:
                    if rec.get("data_quality_status") != primary.get("data_quality_status"):
                        mismatches.append({"day": day, "action": action, "reason": "status"})
                    continue
                if abs(float(rec["net_r"]) - float(primary["net_r"])) > 1e-8:
                    mismatches.append(
                        {
                            "day": day,
                            "action": action,
                            "primary": primary["net_r"],
                            "independent": rec["net_r"],
                        }
                    )
                if action == "BUY":
                    if rec["entry_fill"] != rec["entry_ask"] or rec["exit_fill"] != rec["exit_bid"]:
                        mismatches.append({"day": day, "action": "BUY", "reason": "fill_convention"})
            if checked >= max_n:
                break
        if checked >= max_n:
            break

    # overlap
    violations = 0
    for day, evs in by_day.items():
        ordered = sorted(evs, key=lambda x: x["decision_idx"])
        for a, b in zip(ordered, ordered[1:]):
            if b["decision_idx"] < a["decision_idx"] + HORIZON_BARS:
                violations += 1

    return {
        "ok": len(mismatches) == 0 and violations == 0,
        "checked_outcomes": checked,
        "n_mismatches": len(mismatches),
        "mismatch_sample": mismatches[:10],
        "overlap_violations": violations,
    }
