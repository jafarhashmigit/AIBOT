"""Evidence sufficiency framework."""

from __future__ import annotations

import json
from typing import Any

from phase69.constants import (
    PROVISIONAL_INDEPENDENT_DATE_TARGET,
    STATUS_ACTIVE,
    STATUS_INSUFFICIENT,
    STATUS_QUALITY_BLOCKED,
    STATUS_THRESHOLD,
    SUFFICIENCY_PATH,
    canonical_json_sha256,
)


def build_sufficiency_report(accounting: dict[str, Any]) -> dict[str, Any]:
    n_dates = int(accounting.get("n_independent_live_dates") or 0)
    live_bars = int(accounting.get("unique_newly_closed_live_m5_bars") or 0)
    quotes = int(accounting.get("live_quote_observations") or 0)
    integrity_ok = bool((accounting.get("journal_integrity") or {}).get("index_matches", True))
    contamination = bool(accounting.get("contamination_detected"))
    runtime = accounting.get("runtime_sec_measured")

    if contamination or not integrity_ok:
        status = STATUS_QUALITY_BLOCKED
        reason = "Contamination or journal integrity failure"
    elif n_dates >= PROVISIONAL_INDEPENDENT_DATE_TARGET and live_bars > 0:
        status = STATUS_THRESHOLD
        reason = (
            f"Provisional engineering checkpoint: ≥{PROVISIONAL_INDEPENDENT_DATE_TARGET} independent "
            "live dates with newly closed bars. NOT a tradable-edge proof."
        )
    elif runtime and float(runtime) > 0 and (quotes > 0 or live_bars >= 0):
        # Collection path works; dates still insufficient
        if n_dates == 0 and live_bars == 0:
            status = STATUS_INSUFFICIENT
            reason = (
                f"Collector ran (runtime_sec={runtime}) but unique newly closed live M5 bars={live_bars}, "
                f"independent live dates={n_dates} (backfill excluded). Quotes={quotes}."
            )
        elif n_dates < PROVISIONAL_INDEPENDENT_DATE_TARGET:
            status = STATUS_ACTIVE if (quotes > 0 or live_bars > 0 or float(runtime) > 0) else STATUS_INSUFFICIENT
            # If only backfill+quotes from short verify, still insufficient but collection active capability
            status = STATUS_INSUFFICIENT if n_dates == 0 else STATUS_ACTIVE
            reason = (
                f"Independent live dates={n_dates}/{PROVISIONAL_INDEPENDENT_DATE_TARGET}; "
                f"newly closed live M5={live_bars}; quotes={quotes}."
            )
        else:
            status = STATUS_THRESHOLD
            reason = "Date threshold reached"
    else:
        status = STATUS_INSUFFICIENT
        reason = "No measured live collection runtime / observations"

    # Prefer ACTIVE when engineering path proven via verify but dates=0
    if status == STATUS_INSUFFICIENT and runtime and float(runtime) > 0 and not contamination and integrity_ok:
        # Explicit: accumulation capability demonstrated; evidence still insufficient
        pass

    out = {
        "status": status,
        "reason": reason,
        "provisional_independent_date_target": PROVISIONAL_INDEPENDENT_DATE_TARGET,
        "n_independent_live_dates": n_dates,
        "unique_newly_closed_live_m5_bars": live_bars,
        "live_quote_observations": quotes,
        "runtime_sec_measured": runtime,
        "reconnect_count": accounting.get("reconnects_observed"),
        "duplicate_suppressed": accounting.get("duplicate_suppressed_verify"),
        "quarantine_n": accounting.get("quarantine_n"),
        "stale_n": accounting.get("stale_n"),
        "journal_integrity_ok": integrity_ok,
        "trading_edge_validated": False,
        "twenty_dates_equals_edge": False,
        "note": (
            "20-date target is an engineering/research sufficiency checkpoint only. "
            "It does not establish statistical independence of a strategy or trading validity."
        ),
        "actual_counts_only": True,
        "estimated_completion_fabricated": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    SUFFICIENCY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUFFICIENCY_PATH.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
