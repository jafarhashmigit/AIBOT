"""Supervised signal-orchestrator service lifecycle."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase16b.secrets import safe_config_status, webhook_configured
from phase54.decision import NullPolicy
from signal_bot.orchestrator.constants import (
    CHAMPION_STATUS,
    DEFAULT_MODE,
    LOG_PATH,
    PID_PATH,
    PRODUCTION_FINAL_ACTION,
    SERVICE_DIR,
    SERVICE_VERSION,
    STATE_PATH,
)
from signal_bot.orchestrator.delivery import DeliveryLedger, DeliveryQueue
from signal_bot.orchestrator.formatter import format_signal_message
from signal_bot.orchestrator.gate import effective_operating_mode, evaluate_publication_gate
from signal_bot.orchestrator.orchestrator import SignalOrchestrator
from signal_bot.orchestrator.contract import build_signal_event


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{_utc()} {msg}\n")
        f.flush()
        os.fsync(f.fileno())


def _write_state(state: dict[str, Any]) -> None:
    SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({**state, "updated_utc": _utc()}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"status": "STOPPED"}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import subprocess as sp

            out = sp.check_output(["tasklist", "/FI", f"PID eq {pid}", "/NH"], text=True, stderr=sp.DEVNULL)
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def single_instance_status() -> dict[str, Any]:
    pid = None
    if PID_PATH.is_file():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            pid = None
    alive = bool(pid and _pid_alive(pid))
    if pid and not alive:
        PID_PATH.unlink(missing_ok=True)
        pid = None
    return {"pid": pid, "pid_alive": alive, "blocked": alive}


def stop_service() -> dict[str, Any]:
    st = single_instance_status()
    pid = st.get("pid")
    if not pid:
        _write_state({"status": "STOPPED"})
        return {"status": "ALREADY_STOPPED"}
    if sys.platform == "win32":
        os.system(f"taskkill /PID {pid} /F >NUL 2>&1")
    else:
        try:
            os.kill(pid, 15)
        except Exception:
            pass
    PID_PATH.unlink(missing_ok=True)
    _write_state({"status": "STOPPED", "stopped_utc": _utc(), "stopped_pid": pid})
    _log(f"STOP pid={pid}")
    return {"status": "STOPPED", "pid": pid}


def health() -> dict[str, Any]:
    st = _read_state()
    inst = single_instance_status()
    ledger = DeliveryLedger()
    queue = DeliveryQueue()
    orch_stats = st.get("stats") or {}
    return {
        "service_status": "RUNNING" if inst["pid_alive"] else "STOPPED",
        "pid": inst.get("pid"),
        "pid_alive": inst.get("pid_alive"),
        "service_version": SERVICE_VERSION,
        "operating_mode": st.get("mode") or DEFAULT_MODE,
        "active_policy": st.get("active_policy") or "NullPolicy",
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "publication_gate_status": "ENFORCING_BLOCK_ACTIONABLE",
        "last_decision": st.get("last_decision"),
        "last_qualified_signal": st.get("last_qualified_signal"),  # always null while champion NO_MODEL
        "last_blocked_signal": st.get("last_blocked"),
        "pending_delivery_count": queue.pending_count(),
        "successful_delivery_count": orch_stats.get("delivered_local"),
        "failed_delivery_count": orch_stats.get("failed"),
        "duplicate_suppression_count": orch_stats.get("duplicates"),
        "network_calls": orch_stats.get("network_calls", 0),
        "discord_connectivity": {
            "webhook_configured": webhook_configured(),
            "value_revealed": False,
            "config": safe_config_status(),
            "note": "SHADOW/DRY_RUN never dial Discord",
        },
        "safety": {
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "order_send": "PROHIBITED",
            "discord_actionable_publication": "DISABLED",
            "live_trading": "NOT_AUTHORIZED",
        },
        "state": st,
    }


def dry_run_preview(event: dict[str, Any] | None = None) -> dict[str, Any]:
    """Local message preview — no network."""
    if event is None:
        event = build_signal_event(
            action="WAIT",
            decision_id="preview_decision",
            strategy_id="NULL_POLICY",
            strategy_version="preview",
            reason_codes=["PREVIEW_ONLY"],
            validation_status="UNVALIDATED",
            risk_check_status="UNAPPROVED",
        )
    gate = evaluate_publication_gate(event, mode=effective_operating_mode("DRY_RUN"))
    payload = format_signal_message(gate["event"], gated=True)
    return {
        "mode": "DRY_RUN",
        "network_called": False,
        "gate": {"status": gate["status"], "block_reasons": gate["block_reasons"]},
        "message": payload,
    }


def shadow_report(limit: int = 20) -> dict[str, Any]:
    from signal_bot.orchestrator.constants import DECISIONS_PATH

    rows = []
    if DECISIONS_PATH.is_file():
        for line in DECISIONS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {
        "n": len(rows),
        "recent": rows[-limit:],
        "network_calls_any": any((r.get("delivery") or {}).get("network_called") for r in rows),
    }


def delivery_history(limit: int = 50) -> dict[str, Any]:
    path = DeliveryLedger().path
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {"n": len(rows), "recent": rows[-limit:]}


def verify_config() -> dict[str, Any]:
    return {
        "mode_default": DEFAULT_MODE,
        "mode_effective": effective_operating_mode(DEFAULT_MODE),
        "webhook": safe_config_status(),
        "champion": CHAMPION_STATUS,
        "publication_authorization_enabled": False,
        "authorized_mode_clamped": True,
    }


def run_loop(
    *,
    mode: str | None = None,
    interval_sec: float = 30.0,
    max_cycles: int | None = None,
    duration_sec: float | None = None,
    market_states: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Foreground loop. Without market_states, records heartbeat WAIT decisions (no fabricated BUY/SELL).
    Does not dial Discord in SHADOW/DRY_RUN.
    """
    inst = single_instance_status()
    if inst["blocked"] and inst["pid"] != os.getpid():
        return {"status": "ALREADY_RUNNING", "pid": inst["pid"]}

    mode_eff = effective_operating_mode(mode)
    SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    orch = SignalOrchestrator(policy=NullPolicy(), mode=mode_eff)
    started = time.time()
    started_utc = _utc()
    _log(f"START mode={mode_eff} policy=NullPolicy")
    cycles = 0
    try:
        while True:
            if duration_sec is not None and (time.time() - started) >= duration_sec:
                break
            if max_cycles is not None and cycles >= max_cycles:
                break
            if market_states is not None:
                if cycles >= len(market_states):
                    break
                ms = market_states[cycles]
            else:
                ms = {
                    "symbol": "XAUUSDm",
                    "timeframe": "M5",
                    "forming_bar": False,
                    "data_quality_status": "OK",
                    "bar_timestamp_utc": _utc(),
                    "evidence_classification": "BROKER_OBSERVED_LIVE_BAR",
                    "market_data_provenance": "ORCHESTRATOR_HEARTBEAT",
                    "validation_status": "UNVALIDATED",
                    "stale": False,
                }
            result = orch.process_market_state(ms)
            cycles += 1
            _write_state(
                {
                    "status": "RUNNING",
                    "pid": os.getpid(),
                    "mode": mode_eff,
                    "active_policy": "NullPolicy",
                    "started_utc": started_utc,
                    "uptime_sec": round(time.time() - started, 3),
                    "cycles": cycles,
                    "stats": orch.stats,
                    "last_decision": orch.last_decision,
                    "last_blocked": orch.last_blocked,
                    "last_qualified_signal": None,
                    "last_delivery_status": (orch.last_delivery or {}).get("status"),
                    "network_calls": orch.stats.get("network_calls"),
                }
            )
            _log(
                f"CYCLE n={cycles} action={result['signal'].get('direction')} "
                f"gate={result['gate']['status']} delivery={result['delivery'].get('status')} net={result['network_called']}"
            )
            if market_states is None:
                time.sleep(max(5.0, float(interval_sec)))
    except KeyboardInterrupt:
        pass
    finally:
        PID_PATH.unlink(missing_ok=True)
        _write_state(
            {
                "status": "STOPPED",
                "mode": mode_eff,
                "stopped_utc": _utc(),
                "runtime_sec": round(time.time() - started, 3),
                "cycles": cycles,
                "stats": orch.stats,
                "network_calls": orch.stats.get("network_calls"),
            }
        )
        _log(f"END cycles={cycles}")
    return {"status": "STOPPED", "cycles": cycles, "stats": orch.stats, "mode": mode_eff, "network_calls": orch.stats["network_calls"]}
