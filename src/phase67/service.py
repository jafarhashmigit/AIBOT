"""Operational continuous read-only Exness collector service.

Reuses Phase66 collect_once + Phase64_5 BrokerEvidenceJournal — no second journal.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_5.journal import BrokerEvidenceJournal
from phase64_6.readonly_adapter import LiveMt5Backend
from phase64_13.schedule import state_at_utc
from phase66.collector import collect_once
from phase66.constants import BROKER_OBSERVED
from phase66.health import build_health_report
from phase66.spread_stats import compute_spread_stats
from phase67.config import CollectorConfig, parse_config
from phase67.constants import (
    ACTIVE_SYMBOL,
    BROKER_NAME,
    COLLECTOR_VERSION,
    DATASET_VERSION,
    DEFAULT_INTERVAL_SEC,
    DEFAULT_M5_LOOKBACK,
    EXPECTED_DEMO_LOGIN,
    EXPECTED_SERVER,
    JOURNAL_ROOT,
    LOG_PATH,
    PID_PATH,
    RUNTIME_MANIFEST,
    SCHEMA_VERSION,
    SERVICE_DIR,
    SERVICE_VERSION,
    STATE_PATH,
    USER_TZ,
    canonical_json_sha256,
)
from phase67.session_evidence import build_session_evidence_report
from phase69.accounting import build_live_evidence_accounting


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pkt_now() -> str:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(USER_TZ)).isoformat()
    except Exception:
        return "PKT_UNAVAILABLE"


def _log(msg: str) -> None:
    SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{_utc()} {msg}\n"
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def _write_state(state: dict[str, Any]) -> None:
    SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    state = {**state, "updated_utc": _utc(), "service_version": SERVICE_VERSION}
    state["sha256"] = canonical_json_sha256({k: v for k, v in state.items() if k != "sha256"})
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"status": "STOPPED"}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, int(pid))
            if not handle:
                # Fallback: tasklist match (OpenProcess can fail on some PIDs)
                import subprocess as sp

                out = sp.check_output(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    text=True,
                    stderr=sp.DEVNULL,
                )
                return str(pid) in out
            exit_code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            kernel32.CloseHandle(handle)
            return bool(ok) and int(exit_code.value) == STILL_ACTIVE
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _list_collector_pids() -> list[int]:
    """Find all phase67.cli run processes (Windows-safe). PID file alone is insufficient."""
    found: list[int] = []
    try:
        import subprocess as sp

        if sys.platform == "win32":
            ps = (
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Where-Object { $_.CommandLine -match 'phase67\\.cli' -and $_.CommandLine -match '\\srun(\\s|$)' } | "
                "ForEach-Object { $_.ProcessId }"
            )
            out = sp.check_output(
                ["powershell", "-NoProfile", "-Command", ps],
                text=True,
                stderr=sp.DEVNULL,
            )
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    found.append(int(line))
        else:
            out = sp.check_output(["ps", "-eo", "pid,args"], text=True)
            for line in out.splitlines():
                if "phase67.cli" in line and " run" in line and "ps -eo" not in line:
                    found.append(int(line.split(None, 1)[0]))
    except Exception:
        pass
    # Only live PIDs count — stale CIM/PID-file ghosts must not block forever
    return sorted({p for p in set(found) if _pid_alive(p)})


def single_instance_status() -> dict[str, Any]:
    pid = None
    if PID_PATH.is_file():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            pid = None
    others = _list_collector_pids()
    alive = bool(pid and _pid_alive(pid))
    if not alive and others:
        pid = others[0]
        alive = True
    if pid and not _pid_alive(pid):
        pid = others[0] if others else None
        alive = bool(pid)
    # Ignore self when caller is the collector process checking peers
    peers = [p for p in others if p != os.getpid()]
    blocked = bool(peers) or (alive and pid is not None and pid != os.getpid() and _pid_alive(pid))
    # If PID file points at dead process and no peers → not blocked
    if not peers and not (pid and _pid_alive(pid) and pid != os.getpid()):
        blocked = False
        if pid and not _pid_alive(pid):
            PID_PATH.unlink(missing_ok=True)
            pid = None
            alive = False
    return {
        "pid": pid if (pid and _pid_alive(pid)) else (peers[0] if peers else None),
        "pid_alive": bool(peers) or (bool(pid) and _pid_alive(pid)),
        "blocked": blocked,
        "collector_pids": peers if peers else ([pid] if pid and _pid_alive(pid) else []),
        "pid_path": str(PID_PATH),
    }


def evidence_counters() -> dict[str, Any]:
    """Genuine live evidence accounting over the existing Phase67 journal."""
    try:
        acc = build_live_evidence_accounting()
        sess = build_session_evidence_report()
    except Exception as exc:
        return {"status": "ACCOUNTING_ERROR", "error": str(exc)}
    # Slim operational view
    return {
        "status": "OK",
        "unique_historical_backfill_m5_bars": acc.get("unique_historical_backfill_m5_bars"),
        "unique_newly_closed_live_m5_bars": acc.get("unique_newly_closed_live_m5_bars"),
        "unique_broker_observed_quotes": acc.get("live_quote_observations"),
        "independent_live_dates": acc.get("n_independent_live_dates"),
        "independent_live_collection_dates": acc.get("independent_live_collection_dates"),
        "independent_complete_asia_london_dates": sess.get("independent_complete_live_dates"),
        "n_independent_complete_asia_london_dates": sess.get("n_independent_complete_live_dates"),
        "incomplete_session_dates": sess.get("incomplete_dates"),
        "duplicate_suppressed_verify": acc.get("duplicate_suppressed_verify"),
        "duplicate_market_identity_extras": sess.get("duplicate_market_identity_extras"),
        "quarantine_n": acc.get("quarantine_n"),
        "rejected_n": acc.get("rejected_n"),
        "conflict_incidents": sess.get("conflict_incidents"),
        "reconnects_or_blocked_cycles": acc.get("reconnects_observed"),
        "runtime_sec_measured": acc.get("runtime_sec_measured"),
        "continuous_uptime_claimed": False,
        "backfill_never_counted_as_live": True,
        "future_target_complete_dates": 20,
        "target_met": sess.get("target_met"),
        "journal_root": acc.get("journal_root"),
        "provenance_counts": acc.get("provenance_counts"),
        "pkt_display_now": _pkt_now(),
        "note": "HISTORICAL_BACKFILL excluded from live; complete dates require Asia+London live purity",
    }


def health_check() -> dict[str, Any]:
    state = _read_state()
    inst = single_instance_status()
    pid = inst["pid"]
    alive = inst["pid_alive"]
    journal = BrokerEvidenceJournal(JOURNAL_ROOT, allow_synthetic=False, store_label="GENUINE")
    events = journal.all_events() if JOURNAL_ROOT.exists() else []
    quotes = [e for e in events if e.get("kind") == "QUOTE_SNAPSHOT"]
    m5 = [e for e in events if e.get("kind") == "M5_BAR"]
    session = state_at_utc(datetime.now(timezone.utc))["state"]
    last = state.get("last_collect")
    hr = build_health_report(last_collect=last, session_state=session, connected=bool(state.get("connected")))
    freshness = None
    last_success = None
    if isinstance(last, dict):
        last_success = last.get("retrieved_at_utc")
        if last_success:
            try:
                dt = datetime.fromisoformat(str(last_success).replace("Z", "+00:00"))
                freshness = round((datetime.now(timezone.utc) - dt).total_seconds(), 3)
            except Exception:
                freshness = None
    evid = evidence_counters()
    last_live_m5 = None
    last_journal_write = None
    live_today = 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from phase69.provenance import classify_record

    try:
        acc = build_live_evidence_accounting()
        started_utc = acc.get("collector_started_utc")
        ended_utc = acc.get("collector_ended_utc")
    except Exception:
        started_utc = state.get("started_utc") if isinstance(state, dict) else None
        ended_utc = None
    for e in m5:
        prov = e.get("evidence_provenance") or classify_record(
            e, collector_started_utc=started_utc, collector_ended_utc=ended_utc
        )
        if prov != "BROKER_OBSERVED_LIVE_BAR":
            continue
        ts = str(e.get("server_timestamp_utc") or "")
        last_live_m5 = ts
        if ts.startswith(today):
            live_today += 1
    if events:
        stamps = [str(e.get("ingested_utc") or e.get("collection_timestamp_utc") or "") for e in events]
        stamps = [s for s in stamps if s]
        last_journal_write = max(stamps) if stamps else None

    last_stats = (last or {}).get("stats") if isinstance(last, dict) else {}
    out = {
        "service_status": "RUNNING" if alive else ("STALE_PID" if pid else "STOPPED"),
        "pid": pid,
        "pid_alive": alive,
        "process_identity": {"pid": pid, "service_version": SERVICE_VERSION, "collector_version": COLLECTOR_VERSION},
        "mt5_connection_state": "CONNECTED" if state.get("connected") else ("UNKNOWN" if alive else "NOT_RUNNING"),
        "broker_symbol_availability": ACTIVE_SYMBOL,
        "session_state": session,
        "journal_n_events": len(events),
        "journal_n_quotes": len(quotes),
        "journal_n_m5": len(m5),
        "journal_integrity": journal.integrity_report() if JOURNAL_ROOT.exists() else {},
        "last_state": state,
        "collection_health": hr,
        "data_freshness_sec": freshness,
        "last_successful_poll_utc": last_success,
        "last_newly_closed_live_m5_bar": last_live_m5,
        "last_journal_write_utc": last_journal_write,
        "live_bars_collected_today": live_today,
        "total_unique_live_bars": evid.get("unique_newly_closed_live_m5_bars") if isinstance(evid, dict) else None,
        "independent_complete_dates": evid.get("n_independent_complete_asia_london_dates")
        if isinstance(evid, dict)
        else None,
        "incomplete_dates": evid.get("incomplete_session_dates") if isinstance(evid, dict) else None,
        "duplicate_and_conflict": {
            "duplicates_last_cycle": (last_stats or {}).get("DUPLICATE_SUPPRESSED"),
            "conflicts_last_cycle": (last_stats or {}).get("CONFLICTING_EVIDENCE"),
            "forming_skipped_last_cycle": (last_stats or {}).get("FORMING_SKIPPED"),
            "journal_conflict_incidents": evid.get("conflict_incidents") if isinstance(evid, dict) else None,
            "duplicate_market_identity_extras": evid.get("duplicate_market_identity_extras")
            if isinstance(evid, dict)
            else None,
        },
        "current_evidence_sufficiency": {
            "target_complete_dates": 20,
            "complete_dates": evid.get("n_independent_complete_asia_london_dates") if isinstance(evid, dict) else 0,
            "sufficient_for_h70_validation": False,
            "note": "Sufficiency requires ≥20 independent complete Asia+London live dates",
        },
        "consecutive_failures": int(state.get("consecutive_failures") or 0),
        "stale_warning": bool(freshness is not None and freshness > float(state.get("stale_data_threshold_sec") or 300)),
        "evidence": evid,
        "log_path": str(LOG_PATH),
        "journal_root": str(JOURNAL_ROOT),
        "broker": BROKER_NAME,
        "symbol": ACTIVE_SYMBOL,
        "superseded_symbol_not_used": "XAUUSD",
        "tick_stream": False,
        "authorizes_execution": False,
        "order_send": "PROHIBITED",
        "champion": "NO_MODEL",
        "production": "WAIT",
        "live_trading": "NOT_AUTHORIZED",
        "risk_policy": "UNAPPROVED",
        "commission": "UNKNOWN",
        "swap": "UNKNOWN_FOR_EXECUTION",
        "margin": "INCOMPLETE",
        "pkt_display_now": _pkt_now(),
        "continuous_uptime_claimed": False,
        "service_uptime_sec": state.get("uptime_sec") if alive else state.get("runtime_sec"),
        "successful_collection_distinct_from_uptime": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def stop_collector(*, force: bool = False) -> dict[str, Any]:
    pids = set(_list_collector_pids())
    file_pid = None
    if PID_PATH.is_file():
        try:
            file_pid = int(PID_PATH.read_text(encoding="utf-8").strip())
            pids.add(file_pid)
        except Exception:
            PID_PATH.unlink(missing_ok=True)
    if not pids:
        _write_state({"status": "STOPPED", "reason": "no_pid"})
        return {"status": "ALREADY_STOPPED"}
    killed: list[int] = []
    errors: list[str] = []
    for pid in sorted(pids):
        try:
            if sys.platform == "win32":
                rc = os.system(f"taskkill /PID {pid} /F >NUL 2>&1")
                killed.append(pid)
                if rc != 0 and not _pid_alive(pid):
                    pass
            else:
                if _pid_alive(pid):
                    os.kill(pid, 15)
                    killed.append(pid)
        except Exception as exc:
            errors.append(f"{pid}:{exc}")
    # Sweep any remaining collectors
    for pid in _list_collector_pids():
        try:
            if sys.platform == "win32":
                os.system(f"taskkill /PID {pid} /F >NUL 2>&1")
            else:
                os.kill(pid, 15)
            if pid not in killed:
                killed.append(pid)
        except Exception as exc:
            errors.append(f"sweep:{pid}:{exc}")
    PID_PATH.unlink(missing_ok=True)
    _write_state(
        {
            "status": "STOPPED",
            "stopped_utc": _utc(),
            "stopped_pids": sorted(pids),
            "killed_pids": killed,
        }
    )
    _log(f"STOP pids={sorted(pids)} killed={killed}")
    return {
        "status": "STOPPED",
        "pid": file_pid,
        "pids": sorted(pids),
        "killed": killed,
        "errors": errors,
    }


def run_loop(
    *,
    interval_sec: float = DEFAULT_INTERVAL_SEC,
    m5_lookback: int = DEFAULT_M5_LOOKBACK,
    max_cycles: int | None = None,
    duration_sec: float | None = None,
    max_retries: int = 5,
    backoff_initial_sec: float = 2.0,
    backoff_max_sec: float = 60.0,
    stale_data_threshold_sec: float = 300.0,
) -> dict[str, Any]:
    """Foreground collection loop. Write PID for stop/health. Single-instance protected."""
    cfg = parse_config(
        interval_sec=interval_sec,
        m5_lookback=m5_lookback,
        max_cycles=max_cycles,
        duration_sec=duration_sec,
        max_retries=max_retries,
        backoff_initial_sec=backoff_initial_sec,
        backoff_max_sec=backoff_max_sec,
        stale_data_threshold_sec=stale_data_threshold_sec,
    )

    # PID-file gate (primary). Process scan is used by stop/health; using it here races with
    # Windows detached spawn and can false-positive ALREADY_RUNNING.
    if PID_PATH.is_file():
        try:
            existing = int(PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            existing = None
        if existing and existing != os.getpid() and _pid_alive(existing):
            return {
                "status": "ALREADY_RUNNING",
                "pid": existing,
                "error": "single_instance_protection",
                "continuous_uptime_claimed": False,
            }
        if existing and not _pid_alive(existing):
            PID_PATH.unlink(missing_ok=True)

    SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    JOURNAL_ROOT.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    PID_PATH.write_text(str(pid) + "\n", encoding="utf-8")
    started = time.time()
    started_utc = _utc()
    _log(
        f"START pid={pid} interval={cfg.interval_sec}s m5_lookback={cfg.m5_lookback} "
        f"ver={COLLECTOR_VERSION} identity=market_identity_v2"
    )
    journal = BrokerEvidenceJournal(JOURNAL_ROOT, allow_synthetic=False, store_label="GENUINE")
    totals = {
        "cycles": 0,
        "INGESTED": 0,
        "DUPLICATE_SUPPRESSED": 0,
        "QUARANTINED": 0,
        "REJECTED": 0,
        "BLOCKED": 0,
        "CONFLICTING_EVIDENCE": 0,
        "ERRORS": 0,
    }
    last_collect: dict[str, Any] | None = None
    stop_reason = "completed"
    consecutive_failures = 0
    backoff = float(cfg.backoff_initial_sec)

    try:
        while True:
            if cfg.duration_sec is not None and (time.time() - started) >= cfg.duration_sec:
                stop_reason = "duration_elapsed"
                break
            if cfg.max_cycles is not None and totals["cycles"] >= cfg.max_cycles:
                stop_reason = "max_cycles"
                break

            cycle_t0 = time.time()
            try:
                backend = LiveMt5Backend()
                result = collect_once(
                    backend,
                    journal,
                    symbol=ACTIVE_SYMBOL,
                    expected_login=EXPECTED_DEMO_LOGIN,
                    expected_server=EXPECTED_SERVER,
                    synthetic=False,
                    watermark_path=JOURNAL_ROOT / "watermark.json",
                    m5_count=cfg.m5_lookback,
                    collector_started_utc=started_utc,
                    collector_cycle=totals["cycles"] + 1,
                )
            except Exception as exc:
                result = {"status": "ERROR", "reason": str(exc), "traceback": traceback.format_exc()[-500:]}
                _log(f"ERROR {exc}")

            last_collect = result
            totals["cycles"] += 1
            if result.get("status") == "OK":
                st = result.get("stats") or {}
                for k in ("INGESTED", "DUPLICATE_SUPPRESSED", "QUARANTINED", "REJECTED", "CONFLICTING_EVIDENCE"):
                    totals[k] = totals.get(k, 0) + int(st.get(k) or 0)
                connected = True
                consecutive_failures = 0
                backoff = float(cfg.backoff_initial_sec)
            else:
                totals["BLOCKED"] += 1
                if result.get("status") == "ERROR":
                    totals["ERRORS"] += 1
                connected = False
                consecutive_failures += 1

            session = result.get("session_state") or state_at_utc(datetime.now(timezone.utc))["state"]
            unavail = result.get("unavailability")
            _write_state(
                {
                    "status": "RUNNING",
                    "pid": pid,
                    "started_utc": started_utc,
                    "uptime_sec": round(time.time() - started, 3),
                    "connected": connected,
                    "session_state": session,
                    "unavailability": unavail,
                    "config": cfg.to_dict(),
                    "consecutive_failures": consecutive_failures,
                    "stale_data_threshold_sec": cfg.stale_data_threshold_sec,
                    "last_collect": {
                        "status": result.get("status"),
                        "reason": result.get("reason"),
                        "stats": result.get("stats"),
                        "retrieved_at_utc": result.get("retrieved_at_utc"),
                        "n_records": result.get("n_records"),
                    },
                    "totals": totals,
                    "market_closed_not_failure": unavail == "UNAVAILABLE_MARKET_CLOSED_OR_BREAK",
                    "authorizes_execution": False,
                    "continuous_uptime_claimed": False,
                }
            )
            _log(
                f"CYCLE n={totals['cycles']} status={result.get('status')} "
                f"ing={result.get('stats', {}).get('INGESTED')} dup={result.get('stats', {}).get('DUPLICATE_SUPPRESSED')} "
                f"conflict={result.get('stats', {}).get('CONFLICTING_EVIDENCE')} sess={session}"
            )

            if consecutive_failures > 0 and consecutive_failures <= cfg.max_retries:
                sleep_for = min(backoff, cfg.backoff_max_sec)
                _log(f"BACKOFF sleep={sleep_for}s failures={consecutive_failures}")
                time.sleep(sleep_for)
                backoff = min(backoff * 2.0, cfg.backoff_max_sec)
            else:
                elapsed = time.time() - cycle_t0
                sleep_for = max(0.0, float(cfg.interval_sec) - elapsed)
                if cfg.max_cycles is not None and totals["cycles"] >= cfg.max_cycles:
                    stop_reason = "max_cycles"
                    break
                if cfg.duration_sec is not None and (time.time() - started) >= cfg.duration_sec:
                    stop_reason = "duration_elapsed"
                    break
                time.sleep(sleep_for)
    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
    finally:
        runtime_sec = round(time.time() - started, 3)
        events = journal.all_events()
        quotes = [e for e in events if e.get("kind") == "QUOTE_SNAPSHOT" and e.get("validation_status") == "OK"]
        m5 = [e for e in events if e.get("kind") == "M5_BAR"]
        dates = sorted({str(e.get("server_timestamp_utc") or "")[:10] for e in events if e.get("server_timestamp_utc")})
        evid = evidence_counters()
        manifest = {
            "manifest_id": f"phase67_runtime_{canonical_json_sha256({'n': len(events), 't': started_utc})[:16]}",
            "broker": BROKER_NAME,
            "server": EXPECTED_SERVER,
            "symbol": ACTIVE_SYMBOL,
            "source_classification": BROKER_OBSERVED,
            "schema_version": SCHEMA_VERSION,
            "collector_version": COLLECTOR_VERSION,
            "dataset_version": DATASET_VERSION,
            "identity_schema_version": "market_identity_v2",
            "started_utc": started_utc,
            "ended_utc": _utc(),
            "runtime_sec_measured": runtime_sec,
            "stop_reason": stop_reason,
            "totals": totals,
            "n_events": len(events),
            "n_quotes": len(quotes),
            "n_m5": len(m5),
            "independent_dates_any_event": dates,
            "evidence_counters": evid,
            "spread_stats": compute_spread_stats(quotes),
            "continuous_uptime_claimed": False,
            "note": "runtime_sec_measured is wall-clock of this process only; not a long-term SLA claim",
            "config": cfg.to_dict(),
        }
        manifest["sha256"] = canonical_json_sha256({k: v for k, v in manifest.items() if k != "sha256"})
        RUNTIME_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        RUNTIME_MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _write_state(
            {
                "status": "STOPPED",
                "pid": pid,
                "started_utc": started_utc,
                "stopped_utc": _utc(),
                "runtime_sec": runtime_sec,
                "stop_reason": stop_reason,
                "totals": totals,
                "last_collect": last_collect,
                "manifest_path": str(RUNTIME_MANIFEST),
                "evidence_counters": evid,
                "continuous_uptime_claimed": False,
            }
        )
        _log(f"END reason={stop_reason} runtime_sec={runtime_sec} events={len(events)}")
        PID_PATH.unlink(missing_ok=True)
    return manifest


def verify_runtime(*, duration_sec: float = 90.0, interval_sec: float = 20.0) -> dict[str, Any]:
    """Bounded live verification — reports measured runtime only."""
    if interval_sec < 5.0:
        interval_sec = 5.0
    return run_loop(interval_sec=interval_sec, m5_lookback=DEFAULT_M5_LOOKBACK, duration_sec=duration_sec)
