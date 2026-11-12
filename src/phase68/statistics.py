"""Statistical reliability — date-block aware; no overclaim on small N."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from phase68.constants import BOOTSTRAP_DRAWS, BOOTSTRAP_SEED, EVENT_STRIDE, OUTCOME_HORIZONS, canonical_json_sha256
from phase68.displacement import _mean, _pct


def _date_block_metric(events: list[dict[str, Any]], horizon: int, metric: str) -> dict[str, Any]:
    """One value per date (mean of that date's event metrics), then bootstrap dates."""
    by_day: dict[str, list[float]] = defaultdict(list)
    for e in events:
        o = e["outcomes"].get(horizon) or {}
        if not o.get("ok"):
            continue
        if metric == "end_return_atr" and o.get("end_return_atr") is not None:
            by_day[e["day"]].append(float(o["end_return_atr"]))
        elif metric == "p_continuation":
            by_day[e["day"]].append(1.0 if o.get("continued") else 0.0)
        elif metric == "p_reversal":
            by_day[e["day"]].append(1.0 if o.get("reversed") else 0.0)

    day_means = {d: sum(vs) / len(vs) for d, vs in by_day.items() if vs}
    days = sorted(day_means)
    if not days:
        return {"n_dates": 0, "point": None, "ci95": None, "feasible": False}

    point = sum(day_means[d] for d in days) / len(days)
    rng = random.Random(BOOTSTRAP_SEED)
    boots = []
    for _ in range(BOOTSTRAP_DRAWS):
        sample = [day_means[rng.choice(days)] for _ in days]
        boots.append(sum(sample) / len(sample))
    boots.sort()
    lo = boots[int(0.025 * (len(boots) - 1))]
    hi = boots[int(0.975 * (len(boots) - 1))]
    return {
        "n_dates": len(days),
        "n_events_in_metric": sum(len(v) for v in by_day.values()),
        "point_date_mean": point,
        "ci95_date_block_bootstrap": [lo, hi],
        "feasible": len(days) >= 5,
        "warning": None if len(days) >= 10 else "SMALL_DATE_N_DO_NOT_OVERCLAIM_SIGNIFICANCE",
    }


def statistical_reliability(bundle: dict[str, Any]) -> dict[str, Any]:
    events = bundle["events"]
    dates = sorted({e["day"] for e in events})
    per_date = []
    for d in dates:
        de = [e for e in events if e["day"] == d]
        ok12 = [e for e in de if (e["outcomes"].get(12) or {}).get("ok")]
        cont = _mean([1.0 if e["outcomes"][12]["continued"] else 0.0 for e in ok12])
        rev = _mean([1.0 if e["outcomes"][12]["reversed"] else 0.0 for e in ok12])
        per_date.append(
            {
                "day": d,
                "n_events": len(de),
                "n_ok_h12": len(ok12),
                "p_cont_h12": cont,
                "p_rev_h12": rev,
                "mean_end_atr_h12": _mean(
                    [e["outcomes"][12]["end_return_atr"] for e in ok12 if e["outcomes"][12].get("end_return_atr") is not None]
                ),
            }
        )

    buy = [e for e in events if e["direction"] == "BUY"]
    sell = [e for e in events if e["direction"] == "SELL"]

    # Overlap / dependence
    overlap_note = (
        f"Events use EVENT_STRIDE={EVENT_STRIDE} so decision indices within a day are non-overlapping "
        f"for horizon≤{EVENT_STRIDE}, but horizon 24 exceeds stride — residual path overlap possible. "
        "Events on the same date share regime; treat date-blocks as the independence unit."
    )

    out = {
        "event_count": len(events),
        "independent_date_count": len(dates),
        "events_per_date": {
            "mean": _mean([p["n_events"] for p in per_date]),
            "min": min((p["n_events"] for p in per_date), default=None),
            "max": max((p["n_events"] for p in per_date), default=None),
            "p50": _pct([float(p["n_events"]) for p in per_date], 0.5),
        },
        "date_level_rows": per_date,
        "date_level_variability_p_cont_h12": {
            "p25": _pct([float(p["p_cont_h12"]) for p in per_date if p["p_cont_h12"] is not None], 0.25),
            "p50": _pct([float(p["p_cont_h12"]) for p in per_date if p["p_cont_h12"] is not None], 0.5),
            "p75": _pct([float(p["p_cont_h12"]) for p in per_date if p["p_cont_h12"] is not None], 0.75),
        },
        "bootstrap_h12": {
            "end_return_atr_all": _date_block_metric(events, 12, "end_return_atr"),
            "p_continuation_all": _date_block_metric(events, 12, "p_continuation"),
            "p_reversal_all": _date_block_metric(events, 12, "p_reversal"),
            "p_continuation_BUY": _date_block_metric(buy, 12, "p_continuation"),
            "p_continuation_SELL": _date_block_metric(sell, 12, "p_continuation"),
            "p_continuation_low_vol": _date_block_metric([e for e in events if e.get("vol_regime") == "low"], 12, "p_continuation"),
            "p_continuation_high_vol": _date_block_metric([e for e in events if e.get("vol_regime") == "high"], 12, "p_continuation"),
        },
        "buy_n": len(buy),
        "sell_n": len(sell),
        "event_overlap_dependence": overlap_note,
        "missing_censoring": {
            "n_boundary_censored_outcome_slots": bundle.get("n_boundary_censored_outcomes"),
            "policy": "Events requiring horizon beyond day end are censored (ok=False); not forward-filled",
        },
        "significance_claim": False,
        "significance_note": (
            "Do not claim statistical significance from small event or date counts. "
            "CIs are descriptive uncertainty under date-block resampling assumptions only."
        ),
        "horizons": list(OUTCOME_HORIZONS),
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k not in ("sha256", "date_level_rows")})
    return out
