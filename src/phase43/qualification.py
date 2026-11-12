"""Phase43 verdict — data readiness only."""

from __future__ import annotations

from typing import Any


def decide_verdict(
    *,
    exposure: dict[str, Any],
    selection: dict[str, Any],
    acquisition: dict[str, Any],
    quality: dict[str, Any],
    indep_ok: bool,
    eligibility: dict[str, Any],
) -> dict[str, Any]:
    if not indep_ok:
        return {
            "final_verdict": "DATA_QUALITY_FAILED",
            "reason": "independent manifest/hash verification failed",
        }

    n_unseen_pool = (exposure.get("summary") or {}).get("n_unseen") or 0
    n_selected = selection.get("selected_n") or 0
    n_ready = eligibility.get("A_n") or 0
    n_complete = quality.get("n_complete_sessions") or 0
    n_acquired = len(acquisition.get("completed_dates") or [])

    if n_unseen_pool == 0 or n_selected == 0:
        return {
            "final_verdict": "NO_INDEPENDENT_DATA_AVAILABLE",
            "reason": f"unseen_pool={n_unseen_pool}, selected={n_selected}",
        }

    if n_ready >= 20 and n_complete >= 20 and quality.get("n_h1_warmup_ok", 0) >= 20:
        return {
            "final_verdict": "INDEPENDENT_DATA_READY",
            "reason": f"ready_unseen_dates={n_ready}, complete_sessions={n_complete}",
        }

    if n_ready >= 5 or n_acquired >= 5:
        return {
            "final_verdict": "PARTIAL_DATA_READY",
            "reason": (
                f"ready_unseen_dates={n_ready}, acquired_complete={n_acquired}, "
                f"pending={acquisition.get('pending_dates')}, stop={acquisition.get('stop_reason')}"
            ),
        }

    if n_acquired == 0 and acquisition.get("stop_reason"):
        return {
            "final_verdict": "DATA_QUALITY_FAILED",
            "reason": f"acquisition failed: {acquisition.get('stop_reason')}",
        }

    return {
        "final_verdict": "NO_INDEPENDENT_DATA_AVAILABLE",
        "reason": f"insufficient ready unseen dates after acquisition (ready={n_ready})",
    }
