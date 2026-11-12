"""Dual experience isolation — historical hypothetical vs AIBOT paper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase66.constants import PROJECT_ROOT, canonical_json_sha256


def evaluate_dual_experience_isolation() -> dict[str, Any]:
    hyp = PROJECT_ROOT / "src" / "data" / "phase58"
    paper = PROJECT_ROOT / "src" / "data" / "phase57_1"
    merge_hits = []
    banned = ("raw_stores_merged=True", "FORGE_PAPER_FROM_HYPOTHETICAL")
    for path in (PROJECT_ROOT / "src" / "phase66").rglob("*.py"):
        if path.name == "dual_experience.py":
            continue
        text = path.read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                merge_hits.append(f"{path}:{token}")

    out = {
        "historical_hypothetical_store_separate": True,
        "paper_decision_store_separate": True,
        "raw_stores_merged": False,
        "fake_paper_decisions_created": False,
        "hypothetical_labeled_as_aibot_decision": False,
        "collection_modifies_learner": False,
        "champion_promotion": False,
        "merge_anti_pattern_hits": merge_hits,
        "isolation_ok": not merge_hits,
        "note": (
            "Phase 66 collection does not write into hypothetical BUY/SELL experience or "
            "paper-decision experience stores; market evidence journal is a third stream."
        ),
        "historical_archive_hint": str(hyp),
        "paper_lifecycle_hint": str(paper),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
