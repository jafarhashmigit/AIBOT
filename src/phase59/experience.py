"""Inspect HISTORICAL_HYPOTHETICAL vs AGENT_SHADOW independently — never merge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase50.experience_store import ExperienceStore
from phase59.constants import SRC_DIR, canonical_json_sha256


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


def _load_best(source: str, roots: list[Path]) -> dict[str, Any]:
    best = {"n": 0, "path": None, "sample": None, "issues": []}
    for root in roots:
        if not root.exists():
            continue
        try:
            st = ExperienceStore(source, root=root)
        except Exception as exc:
            best["issues"].append({"root": str(root), "error": str(exc)})
            continue
        if st.n >= best["n"]:
            recs = st.all()
            # integrity checks
            bad_src = [r.get("experience_id") for r in recs if r.get("source") != source]
            null_net = sum(1 for r in recs if r.get("actual_costed_outcome_net_r") is None)
            sample = None
            if recs:
                r0 = recs[0]
                sample = {
                    "experience_id": r0.get("experience_id"),
                    "action": r0.get("action"),
                    "net_r": r0.get("actual_costed_outcome_net_r"),
                    "decision_context_keys": sorted((r0.get("decision_context") or {}).keys()),
                    "commission_field_present": "commission" in r0,
                }
            best = {
                "n": st.n,
                "path": str(st.path),
                "sample": sample,
                "issues": best["issues"],
                "n_wrong_source": len(bad_src),
                "n_null_net_r": null_net,
                "actions": {
                    "BUY": sum(1 for r in recs if r.get("action") == "BUY"),
                    "SELL": sum(1 for r in recs if r.get("action") == "SELL"),
                    "WAIT": sum(1 for r in recs if r.get("action") == "WAIT"),
                },
            }
    return best


def reconcile_experience() -> dict[str, Any]:
    hist = _load_best("HISTORICAL_HYPOTHETICAL", HIST_CANDIDATES)
    shadow = _load_best("AGENT_SHADOW", SHADOW_CANDIDATES)
    overlap = []
    # id overlap if both loaded
    try:
        if hist.get("path") and shadow.get("path"):
            h = ExperienceStore("HISTORICAL_HYPOTHETICAL", root=Path(hist["path"]).parent)
            s = ExperienceStore("AGENT_SHADOW", root=Path(shadow["path"]).parent)
            hi = {r.get("experience_id") for r in h.all()}
            si = {r.get("experience_id") for r in s.all()}
            overlap = list(hi & si)[:5]
    except Exception as exc:
        overlap = [f"error:{exc}"]

    out = {
        "historical_hypothetical": hist,
        "agent_shadow": shadow,
        "id_overlap_sample": overlap,
        "stores_merged": False,
        "phase58_shadow_force_align": False,
        "differences": [
            "Historical store holds counterfactual BUY/SELL(/WAIT) matured outcomes from market path",
            "Shadow store holds agent paper decisions/outcomes when present",
            "Shadow n may include WAIT engineering records; not an edge dataset",
            "Commission/slippage not present as measured fields in experience schema net_r",
        ],
        "limitations": [
            "Do not treat larger n as better intelligence",
            "Do not force-align Phase58-noted ~86 shadow records into a trading edge",
        ],
    }
    out["experience_sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "experience_sha256"})
    return out
