"""Independent recomputation — reload disk, rebuild features, re-detect events, recompute metrics."""

from __future__ import annotations

from typing import Any

from phase42.constants import VALIDATION_DATES
from phase42.data import list_days, load_h1, load_m5, load_ticks_hours, ticks_by_m5_bar
from phase42.evaluate import _predictive_for_hypothesis
from phase42.features import build_feature_rows
from phase42.hypotheses import frozen_hypothesis_registry
from phase42.labels import attach_forward_labels


def _rebuild_corpus() -> dict[str, list[dict[str, Any]]]:
    corpus = {}
    for day in list_days():
        bars = load_m5(day)
        h1 = load_h1(day)
        ticks_by = ticks_by_m5_bar(load_ticks_hours(day))
        rows = attach_forward_labels(build_feature_rows(list(bars), list(h1), ticks_by))
        corpus[day] = rows
    return corpus


def verify_independent(primary: dict[str, Any]) -> dict[str, Any]:
    registry = frozen_hypothesis_registry()
    corpus = _rebuild_corpus()
    mismatches = []
    matches = 0
    details = []
    for hyp in registry["hypotheses"]:
        hid = hyp["id"]
        indep_val = _predictive_for_hypothesis(hid, hyp, corpus, VALIDATION_DATES, split="validation")
        prim = next((r for r in primary.get("results") or [] if r["hypothesis_id"] == hid), None)
        if prim is None:
            mismatches.append({"hypothesis_id": hid, "reason": "missing_primary"})
            continue
        pval = prim.get("validation") or {}
        ok = (
            pval.get("n_events") == indep_val.get("n_events")
            and abs(float(pval.get("effect") or 0) - float(indep_val.get("effect") or 0)) < 1e-9
            and pval.get("n_dates") == indep_val.get("n_dates")
        )
        details.append(
            {
                "hypothesis_id": hid,
                "ok": ok,
                "primary_n": pval.get("n_events"),
                "indep_n": indep_val.get("n_events"),
                "primary_effect": pval.get("effect"),
                "indep_effect": indep_val.get("effect"),
            }
        )
        if ok:
            matches += 1
        else:
            mismatches.append(details[-1])
    return {
        "ok": len(mismatches) == 0,
        "n_matched": matches,
        "n_hypotheses": len(registry["hypotheses"]),
        "mismatches": mismatches[:20],
        "details": details,
        "method": "fresh disk reload + feature rebuild + label rebuild + trigger re-detect",
    }
