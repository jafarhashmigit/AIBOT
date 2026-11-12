"""Final verdict selection for Phase38 data engine."""

from __future__ import annotations

from typing import Any


def decide_verdict(evidence: dict[str, Any]) -> dict[str, Any]:
    indep = evidence.get("independent") or {}
    acq = evidence.get("acquisition") or {}
    coverage = evidence.get("coverage") or {}
    conn = evidence.get("connection") or {}
    safety = evidence.get("safety") or {}

    connected = conn.get("status") == "connected_readonly"
    indep_ok = bool(indep.get("ok"))
    has_chunks = int((evidence.get("counts") or {}).get("m5_record_count") or 0) > 0 and int(
        (evidence.get("counts") or {}).get("tick_record_count") or 0
    ) > 0
    coverage_documented = bool(coverage.get("probes"))
    safety_ok = bool(safety.get("pass"))
    completed = len(acq.get("completed_days") or [])

    quality_blocked = False
    # If we saved chunks but independent hash/reload failed → blocked
    if has_chunks and not indep_ok:
        quality_blocked = True

    if not connected and not has_chunks:
        verdict = "DATA_QUALITY_BLOCKED"
        reason = "MT5 unavailable and no canonical chunks"
    elif quality_blocked or not safety_ok:
        verdict = "DATA_QUALITY_BLOCKED"
        reason = "independent verification or safety failed"
    elif has_chunks and indep_ok and coverage_documented and completed >= 1:
        # READY does not require full history complete
        if completed >= 5 and indep_ok:
            verdict = "CANONICAL_DATA_ENGINE_READY"
            reason = "engine operational with manifests/hashes/independent reload; coverage limitations documented"
        else:
            verdict = "PARTIALLY_READY"
            reason = f"engine works but only {completed} representative dates completed in budget"
    else:
        verdict = "PARTIALLY_READY"
        reason = "incomplete acquisition or missing documentation artifacts"

    return {
        "final_verdict": verdict,
        "reason": reason,
        "gates": {
            "connected_or_cached": connected or has_chunks,
            "independent_reload_ok": indep_ok,
            "has_m5_and_ticks": has_chunks,
            "coverage_documented": coverage_documented,
            "safety_ok": safety_ok,
            "completed_representative_dates": completed,
        },
    }
