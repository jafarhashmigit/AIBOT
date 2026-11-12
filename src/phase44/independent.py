"""Independent recomputation — reload corpus and re-evaluate without primary objects."""

from __future__ import annotations

from typing import Any

from phase44.corpus import build_corpus
from phase44.evaluate import predictive_eval
from phase44.hypotheses import primary_hypotheses


def verify_independent(primary_discovery: dict[str, Any], dates: list[str]) -> dict[str, Any]:
    corpus = build_corpus(dates, need_ticks=True)
    details = []
    mismatches = []
    for hyp in primary_hypotheses():
        hid = hyp["id"]
        indep = predictive_eval(hid, hyp, corpus, dates, split="discovery_indep")
        prim = next((r for r in primary_discovery.get("results") or [] if r["hypothesis_id"] == hid), None)
        if prim is None:
            mismatches.append({"hypothesis_id": hid, "reason": "missing_primary"})
            continue
        p = prim.get("discovery_predictive") or {}
        ok = p.get("n_events") == indep.get("n_events") and abs(float(p.get("effect") or 0) - float(indep.get("effect") or 0)) < 1e-9
        details.append(
            {
                "hypothesis_id": hid,
                "ok": ok,
                "primary_n": p.get("n_events"),
                "indep_n": indep.get("n_events"),
                "primary_effect": p.get("effect"),
                "indep_effect": indep.get("effect"),
            }
        )
        if not ok:
            mismatches.append(details[-1])
    return {
        "ok": len(mismatches) == 0,
        "n_matched": sum(1 for d in details if d["ok"]),
        "n_hypotheses": len(details),
        "mismatches": mismatches,
        "details": details,
        "method": "fresh Phase43 reload + feature/label rebuild + trigger re-detect",
    }
