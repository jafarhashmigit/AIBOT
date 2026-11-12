"""Separate HISTORICAL_HYPOTHETICAL vs AGENT_SHADOW stores — never merge."""

from __future__ import annotations

from typing import Any

from phase47.constants import DATA_OUT_DIR, RECIPE_ID
from phase47.progress import append_jsonl, write_json


def write_experience_stores(
    *,
    historical_rows: list[dict[str, Any]],
    policy_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    A. HISTORICAL_HYPOTHETICAL — counterfactual outcomes used for training/eval
    B. AGENT_SHADOW — empty scaffold for future actual agent decisions (not fabricated)
    """
    hist_path = DATA_OUT_DIR / "HISTORICAL_HYPOTHETICAL" / "experiences.jsonl"
    shadow_dir = DATA_OUT_DIR / "AGENT_SHADOW"
    shadow_path = shadow_dir / "experiences.jsonl"
    shadow_meta = shadow_dir / "README.json"

    # Compact historical records (not full tick paths)
    hist = []
    for r in historical_rows:
        hist.append(
            {
                "store": "HISTORICAL_HYPOTHETICAL",
                "recipe_id": RECIPE_ID,
                "day": r.get("day"),
                "decision_bar": r.get("decision_bar"),
                "action": r.get("action"),
                "net_r": r.get("net_r"),
                "gross_r": r.get("gross_r"),
                "source": "phase46_outcomes",
                "label": "EXPLORATORY_EXPOSED",
            }
        )
    append_jsonl(hist_path, hist)

    # Do NOT fabricate shadow experiences — empty file + explicit meta
    append_jsonl(shadow_path, [])
    meta = {
        "store": "AGENT_SHADOW",
        "n_experiences": 0,
        "populated": False,
        "note": (
            "Phase47 does not claim online adaptive learning. "
            "AGENT_SHADOW remains empty until real agent shadow decisions exist. "
            "Never copy HISTORICAL_HYPOTHETICAL into this store."
        ),
        "policy_decision_log_separate": str((DATA_OUT_DIR / "policy_decisions_oof.jsonl").as_posix()),
    }
    write_json(shadow_meta, meta)

    # Log OOF policy decisions as research artifacts (not AGENT_SHADOW experiences)
    pol_path = DATA_OUT_DIR / "policy_decisions_oof.jsonl"
    append_jsonl(pol_path, policy_decisions)

    return {
        "historical_path": str(hist_path.as_posix()),
        "historical_n": len(hist),
        "agent_shadow_path": str(shadow_path.as_posix()),
        "agent_shadow_n": 0,
        "stores_merged": False,
        "online_learning_claimed": False,
    }
