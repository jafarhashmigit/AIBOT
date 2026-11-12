"""Competing continuation vs mean-reversion from the SAME displacement events."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from phase68.constants import OUTCOME_HORIZONS, canonical_json_sha256
from phase68.displacement import _mean, _pct


def competing_outcomes_report(bundle: dict[str, Any]) -> dict[str, Any]:
    events = bundle["events"]
    # Same event universe — continuation and reversion are competing labels, not 2N samples
    rows = []
    for e in events:
        o12 = e["outcomes"].get(12) or {}
        if not o12.get("ok"):
            continue
        # Reversion = opposite path end (already in continued/reversed flags)
        rows.append(
            {
                "day": e["day"],
                "direction": e["direction"],
                "vol_regime": e.get("vol_regime"),
                "session_state": e["session_state"],
                "h12": o12,
                "h3": e["outcomes"].get(3) or {},
                "h6": e["outcomes"].get(6) or {},
            }
        )

    counts = Counter()
    for r in rows:
        h = r["h12"]
        if h.get("initially_continue_then_reverse"):
            counts["initially_continue_then_reverse"] += 1
        if h.get("initially_reverse_then_continue"):
            counts["initially_reverse_then_continue"] += 1
        if h.get("no_meaningful_move"):
            counts["no_meaningful_directional_move_h12"] += 1
        if h.get("mae_before_meaningful_mfe"):
            counts["large_adverse_before_favourable"] += 1
        if h.get("continued"):
            counts["terminal_continuation_h12"] += 1
        if h.get("reversed"):
            counts["terminal_reversal_h12"] += 1

    # Distributions of end_return_atr
    cont_atr = [r["h12"]["end_return_atr"] for r in rows if r["h12"].get("continued") and r["h12"].get("end_return_atr") is not None]
    rev_atr = [r["h12"]["end_return_atr"] for r in rows if r["h12"].get("reversed") and r["h12"].get("end_return_atr") is not None]
    flat_atr = [r["h12"]["end_return_atr"] for r in rows if r["h12"].get("flat") and r["h12"].get("end_return_atr") is not None]

    # Horizon agreement: continue at h3 then reverse at h12
    path_flip = Counter()
    for r in rows:
        h3, h12 = r["h3"], r["h12"]
        if not (h3.get("ok") and h12.get("ok")):
            continue
        if h3.get("continued") and h12.get("reversed"):
            path_flip["h3_cont_h12_rev"] += 1
        elif h3.get("reversed") and h12.get("continued"):
            path_flip["h3_rev_h12_cont"] += 1
        elif h3.get("continued") and h12.get("continued"):
            path_flip["h3_cont_h12_cont"] += 1
        elif h3.get("reversed") and h12.get("reversed"):
            path_flip["h3_rev_h12_rev"] += 1
        else:
            path_flip["mixed_flat"] += 1

    by_dir = defaultdict(Counter)
    for r in rows:
        d = r["direction"]
        h = r["h12"]
        if h.get("continued"):
            by_dir[d]["continuation"] += 1
        if h.get("reversed"):
            by_dir[d]["reversal"] += 1
        if h.get("flat"):
            by_dir[d]["flat"] += 1

    out = {
        "note": (
            "Continuation and mean-reversion are competing outcomes of the SAME displacement events. "
            "Do not add their counts as independent samples (N is not doubled)."
        ),
        "n_unique_events": len(rows),
        "n_independent_dates": len({r["day"] for r in rows}),
        "path_shape_counts": dict(counts),
        "horizon_flip_counts": dict(path_flip),
        "by_direction_terminal_h12": {k: dict(v) for k, v in by_dir.items()},
        "end_return_atr_distributions_h12": {
            "continuation": {
                "n": len(cont_atr),
                "mean": _mean(cont_atr),
                "p25": _pct(cont_atr, 0.25),
                "p50": _pct(cont_atr, 0.5),
                "p75": _pct(cont_atr, 0.75),
            },
            "reversal": {
                "n": len(rev_atr),
                "mean": _mean(rev_atr),
                "p25": _pct(rev_atr, 0.25),
                "p50": _pct(rev_atr, 0.5),
                "p75": _pct(rev_atr, 0.75),
            },
            "flat": {
                "n": len(flat_atr),
                "mean": _mean(flat_atr),
                "p25": _pct(flat_atr, 0.25),
                "p50": _pct(flat_atr, 0.5),
                "p75": _pct(flat_atr, 0.75),
            },
        },
        "horizons_evaluated": list(OUTCOME_HORIZONS),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
