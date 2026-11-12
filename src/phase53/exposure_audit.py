"""Date-level exposure ledger from Phase43–52 manifests (read-only)."""

from __future__ import annotations

import json
from typing import Any

from phase44.constants import DISCOVERY_DATES as P44_DISCOVERY
from phase44.constants import VALIDATION_DATES as P44_VALIDATION
from phase53.constants import (
    PHASE43_EXPOSURE,
    PHASE43_SELECTION,
    PHASE44_ALLOCATION,
    PHASE49_SELECTION,
    PHASE51_SELECTION,
    REPORTS_DIR,
)
from phase53.progress import write_json


def _load(path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_exposure_ledger() -> dict[str, Any]:
    p43_sel = set(_load(PHASE43_SELECTION).get("selected_dates") or [])
    p49 = _load(PHASE49_SELECTION)
    p49_disc = set(p49.get("discovery_dates") or [])
    p49_conf = set(p49.get("confirmation_dates") or [])
    p51_sel = set(_load(PHASE51_SELECTION).get("selected_dates") or [])
    p44_disc = set(P44_DISCOVERY)
    p44_val = set(P44_VALIDATION)
    alloc = _load(PHASE44_ALLOCATION) if PHASE44_ALLOCATION.is_file() else {}

    exposure = _load(PHASE43_EXPOSURE)
    rows_out: list[dict[str, Any]] = []
    class_counts: dict[str, int] = {}

    for r in exposure.get("in_window_rows") or []:
        day = r["date"]
        tags: list[str] = []
        classification = "GENUINELY_UNSEEN_ELIGIBLE"

        if day in p44_val:
            tags.append("phase44_validation_sealed")
            classification = "PREVIOUSLY_USED_VALIDATION"
        elif day in p49_conf:
            tags.append("phase49_confirmation_sealed_do_not_open")
            classification = "SEALED_CONFIRMATION"
        elif day in p51_sel:
            tags.append("phase51_confirmation_do_not_fit")
            classification = "SEALED_CONFIRMATION"
        elif day in p44_disc or day in p43_sel:
            tags.append("phase43_44_discovery_selected")
            classification = "PREVIOUSLY_USED_DISCOVERY_TRAINING"
        elif day in p49_disc:
            tags.append("phase49_50_discovery")
            classification = "PREVIOUSLY_USED_DISCOVERY_TRAINING"
        else:
            cls = r.get("exposure_class")
            if cls == "PARTIALLY_EXPOSED":
                tags.append("phase43_partial")
                classification = "UNKNOWN_EXPOSURE"
            elif cls == "PREVIOUSLY_EXPOSED":
                tags.append("phase43_previously_exposed")
                classification = "PREVIOUSLY_USED_DISCOVERY_TRAINING"
            elif cls == "UNKNOWN":
                tags.append("phase43_unknown")
                classification = "UNKNOWN_EXPOSURE"
            elif cls != "UNSEEN" or not r.get("independent_validation_eligibility"):
                tags.append(f"phase43_{cls}")
                classification = "UNKNOWN_EXPOSURE"
            else:
                tags.append("eligible_remaining_pool")
                classification = "GENUINELY_UNSEEN_ELIGIBLE"

        class_counts[classification] = class_counts.get(classification, 0) + 1
        rows_out.append(
            {
                "date": day,
                "classification": classification,
                "tags": tags,
                "phase43_exposure_class": r.get("exposure_class"),
                "independent_validation_eligibility": r.get("independent_validation_eligibility"),
            }
        )

    eligible = sorted(x["date"] for x in rows_out if x["classification"] == "GENUINELY_UNSEEN_ELIGIBLE")
    never_open = sorted(p44_val | p49_conf)

    report: dict[str, Any] = {
        "algorithm": (
            "Classify every Phase43 in-window weekday using Phase43 selection, Phase44 discovery/validation, "
            "Phase49 discovery/confirmation, Phase50 discovery reuse of Phase49, Phase51 confirmation, "
            "and Phase52 (no strategy dates). Never treat archive presence as independence."
        ),
        "phase44_allocation_lock_present": bool(alloc),
        "class_counts": class_counts,
        "eligible_unseen_n": len(eligible),
        "eligible_unseen_dates": eligible,
        "never_open_dates_n": len(never_open),
        "never_open_dates": never_open,
        "phase51_confirmation_excluded_from_fit": sorted(p51_sel),
        "phase50_note": "Phase50 used Phase49 discovery only; no new date selection.",
        "phase52_note": "Phase52 selected XAUUSD/M5 substrate; no strategy date selection.",
        "rows": rows_out,
    }
    write_json(REPORTS_DIR / "exposure_ledger.json", report)
    return report
