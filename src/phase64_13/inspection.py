"""Initial Phase 64.12 inspection — document CLOSE_ONLY collapse defect."""

from __future__ import annotations

from typing import Any

from phase64_12 import constants as c6412
from phase64_12.schedule import WINTER_WEEKLY, build_verified_schedule_spec
from phase64_12.session_model import build_session_model
from phase64_13.constants import (
    BREAK,
    CLOSE_ONLY,
    PHASE64_12_DEFECT,
    SESSION_STATES,
    canonical_json_sha256,
)


def inspect_phase64_12_implementation() -> dict[str, Any]:
    spec = build_verified_schedule_spec()
    model = build_session_model()
    # Detect collapse: any winter segment labeled BREAK that sits in known Close Only windows
    close_only_like = []
    for wd, segs in WINTER_WEEKLY.items():
        for seg in segs:
            if seg["state"] == BREAK:
                close_only_like.append({"weekday": wd, **seg})

    has_close_only_constant = hasattr(c6412, "CLOSE_ONLY") or CLOSE_ONLY in getattr(c6412, "__dict__", {})
    # phase64_12 constants: OPEN, CLOSED, BREAK, UNKNOWN — no CLOSE_ONLY
    c6412_states = [
        getattr(c6412, n, None)
        for n in ("OPEN", "CLOSED", "BREAK", "UNKNOWN", "CLOSE_ONLY")
    ]

    defect_confirmed = (
        spec.get("close_only_mapped_to") == BREAK
        and CLOSE_ONLY not in (model.get("states") or [])
        and all(s["state"] == BREAK for s in close_only_like)
        and c6412_states[4] is None  # CLOSE_ONLY missing
    )

    out = {
        "phase64_12_verdict_expected": "XAUUSDm_SESSION_EVIDENCE_VALIDATED",
        "close_only_independent_in_64_12": False,
        "close_only_collapsed_into": BREAK,
        "defect_confirmed": defect_confirmed,
        "defect_description": PHASE64_12_DEFECT,
        "phase64_12_states_observed": [s for s in c6412_states[:4] if s],
        "phase64_12_close_only_mapped_to": spec.get("close_only_mapped_to"),
        "phase64_12_model_states": model.get("states"),
        "winter_break_labeled_segments": close_only_like,
        "phase64_13_canonical_states": list(SESSION_STATES),
        "remediation": (
            "Phase 64.13 introduces independent CLOSE_ONLY; remaps published Close Only "
            "intervals; maps intraday published Closed gaps to BREAK; keeps weekly closure as CLOSED. "
            "Phase 64.12 artifacts remain unchanged."
        ),
        "already_correct": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
