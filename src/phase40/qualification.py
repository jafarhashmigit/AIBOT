"""Coverage readiness verdict."""

from __future__ import annotations

from typing import Any


def decide_verdict(
    *,
    phase38_ok: bool,
    indep_ok: bool,
    alignment: dict[str, Any],
    readiness: dict[str, Any],
    acquisition: dict[str, Any],
) -> dict[str, Any]:
    if not phase38_ok:
        return {
            "final_verdict": "DATA_QUALITY_BLOCKED",
            "reason": "Phase38 integrity audit failed",
        }
    if not indep_ok:
        return {
            "final_verdict": "DATA_QUALITY_BLOCKED",
            "reason": "independent manifest/hash verification failed",
        }

    n_complete = int(alignment.get("n_complete_tick_sessions") or 0)
    n_h1 = int(alignment.get("n_h1_warmup_ok") or 0)
    n_ema = int(alignment.get("n_ema20_ready") or 0)
    mr_dates = int((readiness.get("mean_reversion") or {}).get("dates_with_any_eligible") or 0)
    h13_dates = int((readiness.get("H13_C") or {}).get("dates_with_any_eligible") or 0)
    completed = len(acquisition.get("completed_dates") or [])

    # READY: enough independent dates with complete sessions + H1 warm-up + eligible paths
    if n_complete >= 5 and n_h1 >= 5 and n_ema >= 5 and mr_dates >= 5 and h13_dates >= 3:
        return {
            "final_verdict": "COVERAGE_READY_FOR_PHASE39_RETEST",
            "reason": (
                f"complete_tick_sessions={n_complete}, h1_warmup_ok={n_h1}, ema20_ready={n_ema}, "
                f"MR_eligible_dates={mr_dates}, H13_eligible_dates={h13_dates}"
            ),
        }

    if completed > 0 or n_complete > 0 or any(
        (acquisition.get("results") or [])
    ):
        return {
            "final_verdict": "PARTIALLY_READY",
            "reason": (
                f"progress but not ready: complete_sessions={n_complete}/10, "
                f"h1_warmup_ok={n_h1}, MR_eligible_dates={mr_dates}, H13_eligible_dates={h13_dates}, "
                f"pending={acquisition.get('pending_dates')}, stop={acquisition.get('stop_reason')}"
            ),
        }

    return {
        "final_verdict": "DATA_QUALITY_BLOCKED",
        "reason": "no successful coverage acquisition",
    }
