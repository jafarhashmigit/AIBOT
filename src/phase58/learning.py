"""Dual-experience learning evaluation — stores remain separate; no champion revival."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from phase50.experience_store import ExperienceStore
from phase58.constants import EXPERIENCE_DIR, SRC_DIR
from phase58.evaluation import calibrate, date_block_bootstrap


def _bucket(feats: dict[str, Any]) -> str:
    loc = feats.get("prior_session_location")
    sa = feats.get("spread_atr")
    loc_b = "unk" if loc is None else ("lo" if loc < 0.33 else ("hi" if loc > 0.66 else "mid"))
    sa_b = "unk" if sa is None else ("hi" if sa > 0.05 else "lo")
    return f"{loc_b}|{sa_b}"


def _chrono_hist_learner(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prior-only bucket means — measurement control, not Phase50 hyperparameter revival."""
    hist: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"BUY": [], "SELL": []})
    out = []
    for e in sorted(events, key=lambda x: (x["day"], x["decision_idx"])):
        b = _bucket(e["features"])
        buy_m = sum(hist[b]["BUY"]) / len(hist[b]["BUY"]) if hist[b]["BUY"] else None
        sell_m = sum(hist[b]["SELL"]) / len(hist[b]["SELL"]) if hist[b]["SELL"] else None
        action = "WAIT"
        if buy_m is not None and sell_m is not None:
            if buy_m > 0.05 and buy_m >= (sell_m or -1e9):
                action = "BUY"
            elif sell_m is not None and sell_m > 0.05 and sell_m > buy_m:
                action = "SELL"
        if action == "WAIT":
            net = 0.0
        else:
            oc = e["buy"] if action == "BUY" else e["sell"]
            net = float(oc["net_r"])
        out.append({"day": e["day"], "action": action, "net_r": net, "policy": "HIST_LEARNER"})
        hist[b]["BUY"].append(float(e["buy"]["net_r"]))
        hist[b]["SELL"].append(float(e["sell"]["net_r"]))
    return out


def _shadow_available() -> dict[str, Any]:
    candidates = [
        EXPERIENCE_DIR / "AGENT_SHADOW",
        SRC_DIR / "data" / "phase57_1" / "AGENT_SHADOW",
        SRC_DIR / "data" / "phase56" / "AGENT_SHADOW",
        SRC_DIR / "data" / "phase54" / "AGENT_SHADOW",
        SRC_DIR / "data" / "phase57" / "AGENT_SHADOW",
    ]
    best_n = 0
    best_path = None
    for root in candidates:
        if not root.exists():
            continue
        try:
            st = ExperienceStore("AGENT_SHADOW", root=root)
            if st.n > best_n:
                best_n = st.n
                best_path = str(st.path)
        except Exception:
            continue
    return {"n": best_n, "path": best_path, "evaluable": best_n >= 30}


def evaluate_learning(events: list[dict[str, Any]]) -> dict[str, Any]:
    frozen = [{"day": e["day"], "action": "WAIT", "net_r": 0.0, "policy": "NO_MODEL_WAIT"} for e in events]
    hist = _chrono_hist_learner(events)
    shadow_meta = _shadow_available()
    if not shadow_meta["evaluable"]:
        shadow = [{"day": e["day"], "action": "WAIT", "net_r": 0.0, "policy": "SHADOW_UNEVALUABLE"} for e in events]
        dual = list(hist)
        dual_note = "dual_equals_hist_because_shadow_unevaluable"
    else:
        # Do not invent shadow→event alignment; report presence only
        shadow = [{"day": e["day"], "action": "WAIT", "net_r": 0.0, "policy": "SHADOW_PRESENT_UNALIGNED"} for e in events]
        dual = list(hist)
        dual_note = "shadow_records_exist_but_not_force_aligned_to_events; dual=hist"

    c0 = calibrate(frozen)
    c1 = calibrate(hist)
    c2 = calibrate(shadow)
    c3 = calibrate(dual)
    incr = (c1.get("expected_net_r_all_decisions") or 0) - (c0.get("expected_net_r_all_decisions") or 0)
    pairs = [(a["day"], float(a["net_r"]) - float(b["net_r"])) for a, b in zip(hist, frozen)]
    boot = date_block_bootstrap(pairs, bonferroni_n=1)
    demonstrates = bool(boot.get("ok") and boot.get("ci95_excludes_zero") and incr > 0)

    return {
        "policies": {
            "NO_MODEL_WAIT": c0,
            "HIST_LEARNER": c1,
            "SHADOW_LEARNER": c2,
            "DUAL": c3,
        },
        "shadow_meta": shadow_meta,
        "dual_note": dual_note,
        "incremental_vs_wait": incr,
        "incremental_bootstrap": boot,
        "demonstrates_learning": demonstrates,
        "stores_merged": False,
        "champion_implication": "NO_MODEL",
    }
