"""Diagnostic baselines only — not strategy discovery. Retired hyps not revived."""

from __future__ import annotations

from typing import Any

from phase46.exposure import exposure_report
from phase46.metrics import summarize_net_r


BASELINE_IDS = (
    "ALWAYS_WAIT",
    "UNCONDITIONAL_BUY",
    "UNCONDITIONAL_SELL",
    "ALTERNATING_BUY_SELL",
)


def _ok_action(rows: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("action") == action and r.get("data_quality_status") == "OK"]


def select_baseline(rows: list[dict[str, Any]], baseline_id: str) -> list[dict[str, Any]]:
    """
    Map decision bars → one action outcome each.
    rows must contain BUY/SELL/WAIT for the same decision bars.
    """
    by_key: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for r in rows:
        key = (str(r.get("day")), str(r.get("decision_bar")))
        by_key.setdefault(key, {})[str(r.get("action"))] = r

    selected: list[dict[str, Any]] = []
    keys = sorted(by_key.keys())
    for i, key in enumerate(keys):
        acts = by_key[key]
        if baseline_id == "ALWAYS_WAIT":
            if "WAIT" in acts:
                selected.append(acts["WAIT"])
        elif baseline_id == "UNCONDITIONAL_BUY":
            if "BUY" in acts and acts["BUY"].get("data_quality_status") == "OK":
                selected.append(acts["BUY"])
        elif baseline_id == "UNCONDITIONAL_SELL":
            if "SELL" in acts and acts["SELL"].get("data_quality_status") == "OK":
                selected.append(acts["SELL"])
        elif baseline_id == "ALTERNATING_BUY_SELL":
            prefer = "BUY" if (i % 2 == 0) else "SELL"
            alt = "SELL" if prefer == "BUY" else "BUY"
            pick = acts.get(prefer) or acts.get(alt)
            if pick and pick.get("data_quality_status") == "OK":
                selected.append(pick)
        else:
            raise ValueError(f"unknown baseline: {baseline_id}")
    return selected


def evaluate_baselines(
    rows: list[dict[str, Any]],
    scenario_ids: list[str],
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "note": (
            "Diagnostic baselines only. Positive/negative EV here does NOT establish "
            "a tradable edge. Engineering dates are Phase44-discovery-exposed."
        ),
        "retired_not_revived": ["H13_C", "mean_reversion", "H42_*", "H44_*"],
        "baselines": {},
    }
    for bid in BASELINE_IDS:
        selected = select_baseline(rows, bid)
        scen = {}
        for sid in scenario_ids:
            scen[sid] = summarize_net_r(selected, scenario_id=sid)
        report["baselines"][bid] = {
            "n_selected": len(selected),
            "exposure": exposure_report(selected),
            "by_scenario": scen,
            "n_ok_buy_universe": len(_ok_action(rows, "BUY")),
            "n_ok_sell_universe": len(_ok_action(rows, "SELL")),
        }
    return report
