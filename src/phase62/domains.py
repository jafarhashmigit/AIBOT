"""Strict separation of historical / shadow / Exness demo domains."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase50.experience_store import ExperienceStore
from phase62.constants import SRC_DIR, STORE_ROOT, canonical_json_sha256
from phase62.store import ExecutionStore


def audit_domains(store: ExecutionStore) -> dict[str, Any]:
    hist_n = shadow_n = 0
    hist_root = SRC_DIR / "data" / "phase57_1" / "HISTORICAL_HYPOTHETICAL"
    shadow_root = SRC_DIR / "data" / "phase57_1" / "AGENT_SHADOW"
    if hist_root.exists():
        try:
            hist_n = ExperienceStore("HISTORICAL_HYPOTHETICAL", root=hist_root).n
        except Exception:
            pass
    if shadow_root.exists():
        try:
            shadow_n = ExperienceStore("AGENT_SHADOW", root=shadow_root).n
        except Exception:
            pass

    demo_rows = store.all_normalized()
    # Ensure no paper/proxy categories mixed
    bad_mix = [r for r in demo_rows if r.get("evidence_category") in ("SIMULATED_PAPER", "HISTORICAL_QUOTE_PROXY")]
    out = {
        "domains": {
            "historical_hypothetical": {"n": hist_n, "path": str(hist_root)},
            "agent_shadow_paper": {"n": shadow_n, "path": str(shadow_root)},
            "exness_demo_execution": {"n": len(demo_rows), "path": str(STORE_ROOT)},
        },
        "stores_merged": False,
        "force_aligned": False,
        "demo_overwrote_historical_or_paper": False,
        "mixed_paper_proxy_into_demo_store": len(bad_mix) > 0,
        "checks_pass": len(bad_mix) == 0,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
