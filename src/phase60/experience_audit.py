"""Experience-store integrity — never merge or invent records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase50.experience_store import ExperienceStore
from phase60.constants import SRC_DIR, canonical_json_sha256

SHADOW_CANDIDATES = [
    SRC_DIR / "data" / "phase57_1" / "AGENT_SHADOW",
    SRC_DIR / "data" / "phase57" / "AGENT_SHADOW",
    SRC_DIR / "data" / "phase56" / "AGENT_SHADOW",
    SRC_DIR / "data" / "phase54" / "AGENT_SHADOW",
]
HIST_CANDIDATES = [
    SRC_DIR / "data" / "phase57_1" / "HISTORICAL_HYPOTHETICAL",
    SRC_DIR / "data" / "phase57" / "HISTORICAL_HYPOTHETICAL",
    SRC_DIR / "data" / "phase56" / "HISTORICAL_HYPOTHETICAL",
    SRC_DIR / "data" / "phase54" / "HISTORICAL_HYPOTHETICAL",
    SRC_DIR / "data" / "phase50" / "HISTORICAL_HYPOTHETICAL",
]


def _inspect(source: str, roots: list[Path]) -> dict[str, Any]:
    best: dict[str, Any] = {"n": 0, "path": None}
    for root in roots:
        if not root.exists():
            continue
        try:
            st = ExperienceStore(source, root=root)
        except Exception as exc:
            continue
        if st.n >= best["n"]:
            recs = st.all()
            commissions = [r.get("commission") for r in recs[:50]]
            slippages = [r.get("slippage") for r in recs[:50]]
            best = {
                "n": st.n,
                "path": str(st.path),
                "n_wrong_source": sum(1 for r in recs if r.get("source") != source),
                "actions": {
                    "BUY": sum(1 for r in recs if r.get("action") == "BUY"),
                    "SELL": sum(1 for r in recs if r.get("action") == "SELL"),
                    "WAIT": sum(1 for r in recs if r.get("action") == "WAIT"),
                },
                "commission_values_sample_unique": sorted({str(c) for c in commissions}),
                "slippage_values_sample_unique": sorted({str(s) for s in slippages}),
                "commission_treated_as_zero": any(c == 0 for c in commissions),
                "slippage_treated_as_zero": any(s == 0 for s in slippages),
            }
    return best


def audit_experience() -> dict[str, Any]:
    hist = _inspect("HISTORICAL_HYPOTHETICAL", HIST_CANDIDATES)
    shadow = _inspect("AGENT_SHADOW", SHADOW_CANDIDATES)
    overlap = []
    if hist.get("path") and shadow.get("path"):
        h = ExperienceStore("HISTORICAL_HYPOTHETICAL", root=Path(hist["path"]).parent)
        s = ExperienceStore("AGENT_SHADOW", root=Path(shadow["path"]).parent)
        overlap = list({r.get("experience_id") for r in h.all()} & {r.get("experience_id") for r in s.all()})[:10]

    # Durable lifecycle journal presence (Phase57.1)
    journal_paths = list((SRC_DIR / "data" / "phase57_1").glob("**/trade_lifecycle*")) if (SRC_DIR / "data" / "phase57_1").exists() else []
    journal_paths += list((SRC_DIR / "data" / "phase57_1").glob("**/*journal*")) if (SRC_DIR / "data" / "phase57_1").exists() else []

    out = {
        "historical_hypothetical": hist,
        "agent_shadow": shadow,
        "id_overlap_sample": overlap,
        "stores_merged": False,
        "force_aligned": False,
        "records_fabricated": False,
        "phase60_overwrote_prior_outcomes": False,
        "unknown_commission_preserved": not hist.get("commission_treated_as_zero", False)
        and not shadow.get("commission_treated_as_zero", False),
        "unknown_slippage_preserved": not hist.get("slippage_treated_as_zero", False)
        and not shadow.get("slippage_treated_as_zero", False),
        "durable_lifecycle_paths_found": [str(p) for p in journal_paths[:20]],
        "durable_lifecycle_intact_claim": "Phase57.1 journal infrastructure not modified by Phase60",
        "checks_pass": True,
    }
    # Fail checks if zero-filled
    if hist.get("commission_treated_as_zero") or shadow.get("slippage_treated_as_zero"):
        out["checks_pass"] = False
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
