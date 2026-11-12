"""CLI: start / stop / health / status / preview / shadow-report / history / verify-config."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from signal_bot.orchestrator.constants import DEFAULT_MODE, SERVICE_DIR
from signal_bot.orchestrator.service import (
    delivery_history,
    dry_run_preview,
    health,
    run_loop,
    shadow_report,
    single_instance_status,
    stop_service,
    verify_config,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="signal_bot.orchestrator.cli", description="AIBOT signal orchestrator")
    sub = p.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start", help="Start orchestrator (background)")
    start.add_argument("--mode", default=DEFAULT_MODE, choices=["DISABLED", "DRY_RUN", "SHADOW"])
    start.add_argument("--interval", type=float, default=30.0)
    start.add_argument("--foreground", action="store_true")

    sub.add_parser("stop")
    sub.add_parser("health")
    sub.add_parser("status")
    sub.add_parser("preview", help="Dry-run message preview (no network)")
    sub.add_parser("shadow-report")
    sub.add_parser("history")
    sub.add_parser("verify-config")

    run = sub.add_parser("run", help="Foreground loop")
    run.add_argument("--mode", default=DEFAULT_MODE, choices=["DISABLED", "DRY_RUN", "SHADOW"])
    run.add_argument("--interval", type=float, default=30.0)
    run.add_argument("--max-cycles", type=int, default=None)
    run.add_argument("--duration", type=float, default=None)

    args = p.parse_args(argv)

    if args.cmd in {"health", "status"}:
        print(json.dumps(health(), indent=2, sort_keys=True, default=str))
        return 0
    if args.cmd == "stop":
        print(json.dumps(stop_service(), indent=2, sort_keys=True))
        return 0
    if args.cmd == "preview":
        print(json.dumps(dry_run_preview(), indent=2, sort_keys=True, default=str))
        return 0
    if args.cmd == "shadow-report":
        print(json.dumps(shadow_report(), indent=2, sort_keys=True, default=str))
        return 0
    if args.cmd == "history":
        print(json.dumps(delivery_history(), indent=2, sort_keys=True, default=str))
        return 0
    if args.cmd == "verify-config":
        print(json.dumps(verify_config(), indent=2, sort_keys=True, default=str))
        return 0
    if args.cmd == "run" or (args.cmd == "start" and args.foreground):
        out = run_loop(
            mode=getattr(args, "mode", DEFAULT_MODE),
            interval_sec=getattr(args, "interval", 30.0),
            max_cycles=getattr(args, "max_cycles", None),
            duration_sec=getattr(args, "duration", None),
        )
        print(json.dumps(out, indent=2, sort_keys=True, default=str))
        return 0 if out.get("status") != "ALREADY_RUNNING" else 2
    if args.cmd == "start":
        inst = single_instance_status()
        if inst.get("blocked"):
            print(json.dumps({"status": "ALREADY_RUNNING", "pid": inst.get("pid")}, indent=2))
            return 2
        # AUTHORIZED never accepted via CLI
        mode = args.mode if args.mode in {"DISABLED", "DRY_RUN", "SHADOW"} else DEFAULT_MODE
        SERVICE_DIR.mkdir(parents=True, exist_ok=True)
        py = sys.executable
        cmd = [
            py,
            "-m",
            "signal_bot.orchestrator.cli",
            "run",
            "--mode",
            mode,
            "--interval",
            str(args.interval),
        ]
        log = SERVICE_DIR / "spawn.log"
        env = {**dict(os_environ()), "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
        creationflags = 0x00000200 if sys.platform == "win32" else 0
        with log.open("a", encoding="utf-8") as lf:
            proc = subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=str(Path(__file__).resolve().parents[3]),
                env=env,
                creationflags=creationflags,
            )
        print(json.dumps({"status": "SPAWNED", "spawn_pid": proc.pid, "mode": mode, "cmd": cmd}, indent=2))
        return 0
    return 1


def os_environ():
    import os

    return os.environ


if __name__ == "__main__":
    raise SystemExit(main())
