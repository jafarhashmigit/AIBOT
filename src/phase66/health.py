"""Collection health — process running ≠ healthy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase66.constants import MAX_STALE_SEC, canonical_json_sha256
from phase66.quality import classify_unavailability
from phase66.schema import utc_now
from phase66.watermark import load_watermark


def build_health_report(
    *,
    last_collect: dict[str, Any] | None,
    session_state: str,
    connected: bool | None = None,
) -> dict[str, Any]:
    wm = load_watermark()
    now = datetime.now(timezone.utc)
    last_success = wm.get("last_success_utc")
    lag_sec = None
    if last_success:
        try:
            lag_sec = (now - datetime.fromisoformat(last_success.replace("Z", "+00:00"))).total_seconds()
        except Exception:
            lag_sec = None

    if connected is None:
        connected = last_collect is not None and last_collect.get("status") == "OK"

    unavail = classify_unavailability(session_state=session_state, connected=bool(connected))
    # Healthy idle during closed market vs broken
    if not connected:
        health = "UNHEALTHY_DISCONNECTED"
    elif last_collect and last_collect.get("status") == "BLOCKED":
        health = "UNHEALTHY_BLOCKED"
    elif session_state in ("CLOSED", "BREAK") and (lag_sec is None or lag_sec < 3600):
        health = "HEALTHY_IDLE_MARKET_UNAVAILABLE"
    elif lag_sec is not None and lag_sec <= MAX_STALE_SEC:
        health = "HEALTHY"
    elif lag_sec is None and last_collect and last_collect.get("status") == "OK":
        health = "HEALTHY"
    else:
        health = "UNHEALTHY_STALE"

    out = {
        "collector_status": health,
        "mt5_connection": "CONNECTED" if connected else "DISCONNECTED",
        "last_successful_observation": last_success,
        "last_quote_server_ts": wm.get("last_quote_server_ts"),
        "last_m5_server_ts": wm.get("last_m5_server_ts"),
        "collection_lag_sec": lag_sec,
        "tick_snapshot_count": wm.get("n_quotes"),
        "bar_count": wm.get("n_m5"),
        "rejected_count": wm.get("n_rejected"),
        "duplicate_count": wm.get("n_duplicates"),
        "current_symbol": "XAUUSDm",
        "current_session_state": session_state,
        "unavailability_class": unavail,
        "process_running_alone_not_healthy": True,
        "report_time_utc": utc_now(),
        "last_collect_status": (last_collect or {}).get("status"),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
