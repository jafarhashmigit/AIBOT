"""One-shot confirmation on sealed dates — only if discovery survivors exist."""

from __future__ import annotations

from typing import Any

from phase49.discovery import evaluate_hypotheses
from phase49.stats import date_block_bootstrap, mean


def run_confirmation(
    *,
    confirmation_events: list[dict[str, Any]],
    survivor_hyps: list[dict[str, Any]],
    frozen_edges: dict[str, dict[str, float]],
) -> dict[str, Any]:
    if not survivor_hyps:
        return {
            "opened": False,
            "reason": "no_discovery_survivors",
            "n_confirmed": 0,
            "confirmed_ids": [],
        }

    edges = {k: (v["lo"], v["hi"]) for k, v in frozen_edges.items()}
    # Restrict hypothesis list to survivors only
    ev = evaluate_hypotheses(
        confirmation_events,
        survivor_hyps,
        freeze_edges=edges,
        fit_edges=False,
    )

    confirmed = []
    for r in ev.get("results") or []:
        if r.get("status") != "EVALUATED":
            continue
        # Confirmation criteria: mean>0, CI95 excludes 0 (not re-Bonferroni shopping), stress mean>0
        boot = r.get("bootstrap") or {}
        stress = r.get("stress_bootstrap") or {}
        ok = bool(
            (r.get("mean_net_r") or 0) > 0
            and boot.get("ok")
            and boot.get("ci95_excludes_zero")
            and boot.get("ci95_low", -1) > 0
            and stress.get("ok")
            and (stress.get("mean") or -1) > 0
        )
        r["confirmed"] = ok
        if ok:
            confirmed.append(r["hypothesis_id"])

    return {
        "opened": True,
        "n_events": len(confirmation_events),
        "n_survivors_tested": len(survivor_hyps),
        "n_confirmed": len(confirmed),
        "confirmed_ids": confirmed,
        "results": ev.get("results"),
        "note": "Opened exactly once after freeze. No retuning.",
    }
