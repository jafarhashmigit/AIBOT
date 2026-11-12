"""CLI for Phase67 Exness collector: start / stop / health / verify / evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from phase67.constants import DEFAULT_INTERVAL_SEC, DEFAULT_M5_LOOKBACK, DEFAULT_VERIFY_RUNTIME_SEC, SERVICE_DIR
from phase67.service import (
    evidence_counters,
    health_check,
    run_loop,
    single_instance_status,
    stop_collector,
    verify_runtime,
)
from phase67.session_evidence import build_session_evidence_report
from phase64_5.journal import BrokerEvidenceJournal
from phase67.constants import JOURNAL_ROOT


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="phase67.cli", description="Exness XAUUSDm read-only collector")
    sub = p.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start", help="Start collector in background (Windows)")
    start.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    start.add_argument("--m5-lookback", type=int, default=DEFAULT_M5_LOOKBACK)
    start.add_argument("--foreground", action="store_true", help="Run in foreground instead of spawning")

    sub.add_parser("stop", help="Stop background collector")
    sub.add_parser("health", help="Health check")
    sub.add_parser("status", help="Alias for health")
    sub.add_parser("evidence", help="Genuine live vs backfill evidence counters")
    sub.add_parser("report", help="Session completeness + integrity report")
    sub.add_parser("rebuild-index", help="Reconstruct dedup + market-identity index from journal")

    verify = sub.add_parser("verify", help="Bounded live verification run (measured runtime)")
    verify.add_argument("--duration", type=float, default=DEFAULT_VERIFY_RUNTIME_SEC)
    verify.add_argument("--interval", type=float, default=20.0)

    run = sub.add_parser("run", help="Foreground loop")
    run.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    run.add_argument("--m5-lookback", type=int, default=DEFAULT_M5_LOOKBACK)
    run.add_argument("--duration", type=float, default=None)
    run.add_argument("--max-cycles", type=int, default=None)

    args = p.parse_args(argv)

    if args.cmd in {"health", "status"}:
        print(json.dumps(health_check(), indent=2, sort_keys=True, default=str))
        return 0
    if args.cmd == "evidence":
        print(json.dumps(evidence_counters(), indent=2, sort_keys=True, default=str))
        return 0
    if args.cmd == "report":
        print(json.dumps(build_session_evidence_report(), indent=2, sort_keys=True, default=str))
        return 0
    if args.cmd == "rebuild-index":
        j = BrokerEvidenceJournal(JOURNAL_ROOT, allow_synthetic=False, store_label="GENUINE")
        idx = j.reconstruct_index()
        print(
            json.dumps(
                {
                    "status": "REBUILT",
                    "n_keys": idx.get("n"),
                    "n_market_ids": idx.get("n_market_ids"),
                    "reconstructed_utc": idx.get("reconstructed_utc"),
                },
                indent=2,
            )
        )
        return 0
    if args.cmd == "stop":
        print(json.dumps(stop_collector(), indent=2, sort_keys=True))
        return 0
    if args.cmd == "verify":
        out = verify_runtime(duration_sec=args.duration, interval_sec=args.interval)
        print(json.dumps(out, indent=2, sort_keys=True, default=str))
        return 0
    if args.cmd == "run" or (args.cmd == "start" and args.foreground):
        out = run_loop(
            interval_sec=getattr(args, "interval", DEFAULT_INTERVAL_SEC),
            m5_lookback=getattr(args, "m5_lookback", DEFAULT_M5_LOOKBACK),
            duration_sec=getattr(args, "duration", None),
            max_cycles=getattr(args, "max_cycles", None),
        )
        print(json.dumps(out, indent=2, sort_keys=True, default=str))
        return 0 if out.get("status") != "ALREADY_RUNNING" else 2
    if args.cmd == "start":
        inst = single_instance_status()
        if inst.get("blocked"):
            print(
                json.dumps(
                    {"status": "ALREADY_RUNNING", "pid": inst.get("pid"), "error": "single_instance_protection"},
                    indent=2,
                )
            )
            return 2
        SERVICE_DIR.mkdir(parents=True, exist_ok=True)
        # Re-check after stop races
        inst2 = single_instance_status()
        if inst2.get("blocked"):
            print(json.dumps({"status": "ALREADY_RUNNING", "detail": inst2}, indent=2))
            return 2
        py = sys.executable
        cmd = [
            py,
            "-m",
            "phase67.cli",
            "run",
            "--interval",
            str(args.interval),
            "--m5-lookback",
            str(args.m5_lookback),
        ]
        log = SERVICE_DIR / "spawn.log"
        env = {k: v for k, v in __import__("os").environ.items()}
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        env["PYTHONNOUSERSITE"] = "1"
        # Prefer CREATE_NEW_PROCESS_GROUP without DETACHED so the child reliably starts;
        # redirect stdio to spawn.log for durability.
        creationflags = 0x00000200 if sys.platform == "win32" else 0  # CREATE_NEW_PROCESS_GROUP
        with log.open("a", encoding="utf-8") as lf:
            lf.write(f"\n--- spawn {_utc_safe()} cmd={cmd} ---\n")
            lf.flush()
            proc = subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=str(Path(__file__).resolve().parents[2]),
                env=env,
                creationflags=creationflags,
                start_new_session=(sys.platform != "win32"),
                close_fds=(sys.platform != "win32"),
            )
        import time as _time

        _time.sleep(2.0)
        print(
            json.dumps(
                {
                    "status": "SPAWNED",
                    "spawn_pid": proc.pid,
                    "cmd": cmd,
                    "python": py,
                    "child_returncode_so_far": proc.poll(),
                    "post_start": single_instance_status(),
                },
                indent=2,
            )
        )
        return 0
    return 1


def _utc_safe() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
