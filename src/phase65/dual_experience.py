"""Dual-experience evaluation — historical hypothetical vs paper-decision; never merge raw stores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase58.evaluation import calibrate, date_block_bootstrap
from phase65.constants import BOOTSTRAP_SEED, PROJECT_ROOT, SRC_DIR, canonical_json_sha256


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def evaluate_dual_experience(discovery_events: list[dict[str, Any]]) -> dict[str, Any]:
    # A: historical hypothetical — already in events as buy/sell outcomes
    hist_buy = [
        {"day": e["day"], "action": "BUY", "net_r": float(e["buy"]["net_r"])}
        for e in discovery_events
        if e["buy"].get("net_r") is not None
    ]
    hist_sell = [
        {"day": e["day"], "action": "SELL", "net_r": float(e["sell"]["net_r"])}
        for e in discovery_events
        if e["sell"].get("net_r") is not None
    ]
    hist_cal = {
        "BUY": calibrate(hist_buy),
        "SELL": calibrate(hist_sell),
        "provenance": "phase65_discovery_counterfactual_path_outcomes",
        "is_genuine_broker_fill": False,
    }

    # B: paper-decision / shadow experience
    shadow_path = SRC_DIR / "data" / "phase56" / "AGENT_SHADOW" / "experiences.jsonl"
    shadow = _load_jsonl(shadow_path)
    paper_cal = {
        "n": len(shadow),
        "path": str(shadow_path),
        "evaluable": len(shadow) > 0,
        "is_genuine_broker_fill": False,
        "note": "Paper/shadow decisions only; not merged into hypothetical store",
    }

    # C: simple combined architecture — if shadow empty, combined == hist policy of always WAIT learning baseline
    wait = calibrate([{"day": e["day"], "action": "WAIT", "net_r": 0.0} for e in discovery_events])
    # no-learning baseline = WAIT
    # hist-alone "learner": pick side with better discovery mean (look-ahead free if we use prior-only —
    # for honesty, report static pick fitted on discovery as DIAGNOSTIC only, not OOS claim)
    buy_m = hist_cal["BUY"]["expected_net_r_all_decisions"] or 0
    sell_m = hist_cal["SELL"]["expected_net_r_all_decisions"] or 0
    diagnostic_side = "BUY" if buy_m >= sell_m else "SELL"
    diag = calibrate(hist_buy if diagnostic_side == "BUY" else hist_sell)
    pairs = [(d["day"], float(d["net_r"])) for d in (hist_buy if diagnostic_side == "BUY" else hist_sell)]
    boot = date_block_bootstrap(pairs, seed=BOOTSTRAP_SEED, bonferroni_n=1)

    improves = bool(
        boot.get("ok")
        and (boot.get("ci95_low") or 0) > 0
        and (diag["expected_net_r_all_decisions"] or 0) > (wait["expected_net_r_all_decisions"] or 0)
    )

    out = {
        "historical_hypothetical": hist_cal,
        "paper_decision_experience": paper_cal,
        "stores_merged": False,
        "no_learning_baseline_WAIT": wait,
        "hist_alone_diagnostic_constant_side": {
            "side": diagnostic_side,
            "cal": diag,
            "bootstrap": boot,
            "note": "Discovery-fitted constant side is diagnostic — not an OOS validated learner",
        },
        "combined": {
            "architecture": "shadow_empty_falls_back_to_hist_diagnostic",
            "shadow_available": paper_cal["evaluable"],
            "result": diag if not paper_cal["evaluable"] else diag,
        },
        "learning_improves_oos_decision_quality": False,  # no OOS learning claim without sealed eval
        "diagnostic_positive_on_discovery": improves,
        "assumption_more_experience_better": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
