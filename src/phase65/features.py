"""Phase65 features — decision-time only; session via Phase64.13."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase49.atr import atr_at
from phase58.features import mid_from_ticks
from phase64_13.constants import OPEN
from phase64_13.schedule import state_at_utc
from phase65.constants import ATR_PERIOD


def compute_phase65_features(
    *,
    m5: list[dict[str, Any]],
    idx: int,
    ticks_by_bar: dict[str, list],
) -> dict[str, Any]:
    bar = m5[idx]
    ts = str(bar["timestamp_utc"])
    ticks = ticks_by_bar.get(ts) or []
    atr = atr_at(m5, idx, ATR_PERIOD)
    spread = None
    if ticks:
        spread = float(ticks[0]["ask"]) - float(ticks[0]["bid"])

    ret_1 = None
    if idx >= 1:
        m0 = mid_from_ticks(ticks_by_bar.get(str(m5[idx - 1]["timestamp_utc"])))
        m1 = mid_from_ticks(ticks)
        if m0 and m1 and m0 > 0:
            ret_1 = (m1 - m0) / m0

    ret_2 = None
    if idx >= 2:
        m0 = mid_from_ticks(ticks_by_bar.get(str(m5[idx - 2]["timestamp_utc"])))
        m1 = mid_from_ticks(ticks)
        if m0 and m1 and m0 > 0:
            ret_2 = (m1 - m0) / m0

    # range compression: mean ((high-low)/atr) over last 6 completed bars ending at idx
    comps: list[float] = []
    if atr and atr > 0:
        for j in range(max(0, idx - 5), idx + 1):
            hi = float(m5[j]["high"])
            lo = float(m5[j]["low"])
            comps.append((hi - lo) / atr)
    range_compression = sum(comps) / len(comps) if comps else None

    # Session state from Exness schedule (research proxy on archive timestamps)
    session_state = "UNKNOWN"
    try:
        # timestamps like 2025-10-07T12:00:00Z
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        session_state = state_at_utc(dt, honor_holidays=True)["state"]
    except Exception:
        session_state = "UNKNOWN"

    return {
        "spread": spread,
        "atr": atr,
        "ret_1bar_mid": ret_1,
        "ret_2bar_mid": ret_2,
        "range_compression": range_compression,
        "session_state": session_state,
        "session_permits_new_entry": session_state == OPEN,
        "bar_timestamp_utc": ts,
        "feature_family_version": "phase65_v1",
        "look_ahead": False,
    }
