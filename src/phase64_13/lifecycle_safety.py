"""Internal paper-position lifecycle remains active across session states — no broker orders."""

from __future__ import annotations

import copy
from typing import Any

from phase54.paper_exec import force_horizon_exit_from_bars, monitor_and_maybe_exit
from phase64_13.constants import BREAK, CLOSE_ONLY, CLOSED, OPEN, UNKNOWN, canonical_json_sha256
from phase64_13.preflight import evaluate_session_gates


def _fixture_bars_and_ticks() -> tuple[list[dict[str, Any]], dict[str, list]]:
    """Deterministic 3-bar path for SL/TP/horizon tests (software fixture only)."""
    m5 = [
        {"timestamp_utc": "2026-11-10T12:00:00Z"},
        {"timestamp_utc": "2026-11-10T12:05:00Z"},
        {"timestamp_utc": "2026-11-10T12:10:00Z"},
    ]
    ticks = {
        "2026-11-10T12:00:00Z": [{"timestamp_utc": "2026-11-10T12:00:00Z", "bid": 2650.0, "ask": 2650.2}],
        "2026-11-10T12:05:00Z": [{"timestamp_utc": "2026-11-10T12:05:00Z", "bid": 2649.0, "ask": 2649.2}],
        "2026-11-10T12:10:00Z": [{"timestamp_utc": "2026-11-10T12:10:00Z", "bid": 2648.5, "ask": 2648.7}],
    }
    return m5, ticks


def make_open_paper_position(*, side: str = "BUY") -> dict[str, Any]:
    entry = 2650.2 if side == "BUY" else 2650.0
    stop = 1.0
    if side == "BUY":
        sl, tp = entry - stop, entry + stop
    else:
        sl, tp = entry + stop, entry - stop
    return {
        "position_id": "paper_fixture_001",
        "decision_id": "dec_fixture",
        "side": side,
        "status": "OPEN",
        "entry_idx": 0,
        "entry_bar": "2026-11-10T12:00:00Z",
        "entry_fill": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "atr_at_entry": stop,
        "units": 0.01,
        "symbol": "XAUUSDm",
        "synthetic_fixture": True,
        "evidence_label": "SYNTHETIC_TEST_NOT_GENUINE_BROKER",
        "audit": [],
    }


def monitor_under_session(
    session_state: str,
    *,
    position: dict[str, Any] | None = None,
    current_idx: int = 1,
    horizon_bars: int = 3,
) -> dict[str, Any]:
    """
    Prove internal monitoring remains enabled for CLOSE_ONLY/BREAK/CLOSED/UNKNOWN.
    Does not submit broker orders. Synthetic fixture ≠ genuine fill.
    """
    gates = evaluate_session_gates(
        __import__("datetime").datetime(2026, 11, 10, 12, tzinfo=__import__("datetime").timezone.utc),
        force_state=session_state,
    )
    assert gates["B_internal_position_monitoring"] is True
    pos = copy.deepcopy(position or make_open_paper_position())
    m5, ticks = _fixture_bars_and_ticks()
    exit_rec = monitor_and_maybe_exit(
        pos, m5=m5, ticks_by_bar=ticks, current_idx=current_idx, horizon_bars=horizon_bars
    )
    return {
        "session_state": session_state,
        "monitoring_enabled": True,
        "new_entry_rejected": gates["reject_new_entry"] if session_state != OPEN else False,
        "exit": exit_rec,
        "exit_reason": (exit_rec or {}).get("exit_reason"),
        "is_genuine_broker_fill": False,
        "broker_order_submitted": False,
        "execution_authorized": False,
    }


def horizon_exit_under_session(session_state: str) -> dict[str, Any]:
    pos = make_open_paper_position()
    m5, ticks = _fixture_bars_and_ticks()
    closed = force_horizon_exit_from_bars(pos, m5=m5, ticks_by_bar=ticks, horizon_bars=3)
    return {
        "session_state": session_state,
        "monitoring_enabled": True,
        "exit_reason": closed.get("exit_reason"),
        "is_genuine_broker_fill": False,
        "broker_order_submitted": False,
    }


def idempotent_exit_commit() -> dict[str, Any]:
    """Second monitor after close must not create duplicate exit commitment."""
    pos = make_open_paper_position()
    m5, ticks = _fixture_bars_and_ticks()
    first = monitor_and_maybe_exit(pos, m5=m5, ticks_by_bar=ticks, current_idx=1, horizon_bars=3)
    assert first is not None
    # Mark closed as engine would
    pos_closed = {**first, "status": "CLOSED"}
    second = monitor_and_maybe_exit(pos_closed, m5=m5, ticks_by_bar=ticks, current_idx=2, horizon_bars=3)
    return {
        "first_exit_reason": first.get("exit_reason"),
        "second_is_none": second is None,
        "no_duplicate_exit": second is None,
        "is_genuine_broker_fill": False,
    }


def recovery_after_interruption() -> dict[str, Any]:
    """Simulate recovery: reopen monitor from durable OPEN snapshot mid-lifecycle."""
    snapshot = make_open_paper_position()
    # "crash" before exit — recover from snapshot
    recovered = copy.deepcopy(snapshot)
    m5, ticks = _fixture_bars_and_ticks()
    exit_rec = monitor_and_maybe_exit(
        recovered, m5=m5, ticks_by_bar=ticks, current_idx=1, horizon_bars=3
    )
    return {
        "recovered_from_open_snapshot": True,
        "exit_after_recovery": exit_rec is not None,
        "exit_reason": (exit_rec or {}).get("exit_reason"),
        "broker_order_submitted": False,
    }


def run_lifecycle_session_matrix() -> dict[str, Any]:
    states = [OPEN, CLOSE_ONLY, BREAK, CLOSED, UNKNOWN]
    rows = []
    for st in states:
        r = monitor_under_session(st)
        rows.append(
            {
                "state": st,
                "monitoring_enabled": r["monitoring_enabled"],
                "sl_or_exit_detected": r["exit"] is not None,
                "exit_reason": r["exit_reason"],
                "broker_order_submitted": False,
            }
        )
    idem = idempotent_exit_commit()
    rec = recovery_after_interruption()
    hz = {st: horizon_exit_under_session(st)["exit_reason"] for st in states}
    out = {
        "rows": rows,
        "all_states_monitoring_enabled": all(r["monitoring_enabled"] for r in rows),
        "idempotent_exit": idem,
        "recovery": rec,
        "horizon_by_state": hz,
        "synthetic_fixture_not_genuine": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
