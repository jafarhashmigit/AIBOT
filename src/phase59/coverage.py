"""Data coverage manifest — what archives cover, what was audited, what was excluded."""

from __future__ import annotations

from typing import Any

from phase59.constants import canonical_json_sha256


def build_coverage_manifest(
    inventory: dict[str, Any],
    integrity: dict[str, Any],
    *,
    research_days: list[str],
    stress_days: list[str],
    wait_days: list[str],
    holdout: list[str],
) -> dict[str, Any]:
    """Assemble auditable coverage without mutating archives."""
    rows = list(integrity.get("rows") or [])
    audited = [r.get("day") for r in rows if r.get("day")]
    gap_days = [r["day"] for r in rows if int(r.get("n_gaps_gt_5m") or 0) > 0]
    excluded_segments: list[dict[str, Any]] = []
    for r in rows:
        for ex in r.get("excluded_observations") or []:
            excluded_segments.append({"day": r.get("day"), **ex})
        if r.get("excluded_reason"):
            excluded_segments.append({"day": r.get("day"), "reason": r.get("excluded_reason")})

    sources = inventory.get("sources") or {}
    source_summary = {
        name: {"n_days": (meta or {}).get("n_days"), "root": (meta or {}).get("root")}
        for name, meta in sources.items()
    }
    union = list(inventory.get("union_days") or [])
    not_deep_audited = sorted(set(union) - set(audited))

    manifest = {
        "symbol": inventory.get("symbol"),
        "date_min": inventory.get("date_min"),
        "date_max": inventory.get("date_max"),
        "union_n_days": inventory.get("union_n_days"),
        "sources": source_summary,
        "deep_tick_audit_days_n": len(audited),
        "deep_tick_audit_days": audited,
        "union_days_not_in_deep_audit": not_deep_audited,
        "union_days_not_in_deep_audit_n": len(not_deep_audited),
        "research_days_n": len(research_days),
        "research_days_note": "preferred archives minus Phase58 sealed holdout",
        "stress_days": stress_days,
        "wait_days": wait_days,
        "phase58_holdout_sealed": list(holdout),
        "holdout_used_in_stress_or_wait": False,
        "gap_days_gt_5m": gap_days,
        "excluded_observation_segments": excluded_segments,
        "integrity_ok_days": integrity.get("n_ok"),
        "total_m5_bars_audited": integrity.get("total_m5_bars"),
        "total_ticks_audited": integrity.get("total_ticks"),
        "conclusions_supported": [
            "M5 OHLC presence and gap timing on audited days",
            "Observed bid/ask spread when ticks present",
            "Demo-archive path fills for stress/WAIT descriptive economics",
        ],
        "conclusions_not_supported": [
            "Live broker commission or slippage as measured truth",
            "Complete multi-year continuous market coverage",
            "Labeled major disruption regimes",
            "Union days outside deep tick audit as tick-complete",
        ],
        "source_data_silently_repaired": False,
    }
    manifest["coverage_sha256"] = canonical_json_sha256(
        {k: v for k, v in manifest.items() if k != "coverage_sha256"}
    )
    return manifest
