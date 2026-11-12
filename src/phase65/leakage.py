"""Leakage / split / session audits."""

from __future__ import annotations

from typing import Any

from phase65.consumption import assert_holdout_sealed
from phase65.constants import canonical_json_sha256


def audit_leakage(
    *,
    discovery_days: list[str],
    validation_days: list[str],
    holdout: list[str],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    used = discovery_days + validation_days
    holdout_hit = sorted(set(used) & set(holdout))
    # chronological
    chrono_ok = sorted(discovery_days) == discovery_days and sorted(validation_days) == validation_days
    chrono_ok = chrono_ok and (not discovery_days or not validation_days or max(discovery_days) < min(validation_days))
    # overlap of days
    day_overlap = sorted(set(discovery_days) & set(validation_days))
    # feature look-ahead flag
    look_ahead = [e for e in events if e.get("features", {}).get("look_ahead")]
    # session states recorded
    states = sorted({e.get("features", {}).get("session_state") for e in events})
    # event horizon non-overlap within day
    by_day: dict[str, list[int]] = {}
    for e in events:
        by_day.setdefault(e["day"], []).append(int(e["decision_idx"]))
    overlap_violations = 0
    for day, idxs in by_day.items():
        idxs = sorted(idxs)
        for a, b in zip(idxs, idxs[1:]):
            if b < a + 12:  # stride should be 12; horizon 12
                overlap_violations += 1

    try:
        assert_holdout_sealed(used, holdout)
        holdout_ok = True
    except RuntimeError:
        holdout_ok = False

    out = {
        "holdout_sealed_ok": holdout_ok and not holdout_hit,
        "holdout_hits": holdout_hit,
        "chronological_split_ok": chrono_ok,
        "discovery_validation_day_overlap": day_overlap,
        "look_ahead_flags": len(look_ahead),
        "session_states_observed": states,
        "overlap_violations": overlap_violations,
        "bid_ask_semantics": "BUY ask→bid / SELL bid→ask via phase49.outcomes",
        "pass": holdout_ok
        and not holdout_hit
        and chrono_ok
        and not day_overlap
        and len(look_ahead) == 0
        and overlap_violations == 0,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
