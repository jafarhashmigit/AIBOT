"""Collector reliability inspection + Windows autostart artifacts (no false reboot claims)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from phase67.constants import (
    JOURNAL_ROOT,
    LOG_PATH,
    PID_PATH,
    PROJECT_ROOT,
    SERVICE_DIR,
    STATE_PATH,
)
from phase67.service import health_check, single_instance_status

from signal_bot.execution_economics.constants import WINDOWS_TASK_NAME, WINDOWS_TASK_SCRIPT


def inspect_collector_reliability() -> dict[str, Any]:
    health = health_check()
    inst = single_instance_status()
    state: dict[str, Any] = {}
    if STATE_PATH.is_file():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            state = {"error": str(exc)}

    log_tail: list[str] = []
    if LOG_PATH.is_file():
        try:
            lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
            log_tail = lines[-30:]
        except Exception:  # noqa: BLE001
            log_tail = []

    # Capability matrix — what is implemented vs actually tested this prompt
    capabilities = {
        "long_duration_operation": {
            "implemented": True,
            "tested_this_prompt": "PARTIAL — collector currently RUNNING; multi-day not yet elapsed",
        },
        "repeated_polling": {
            "implemented": True,
            "tested_this_prompt": bool((state.get("totals") or {}).get("cycles")),
        },
        "temporary_mt5_disconnection": {
            "implemented": True,
            "tested_this_prompt": False,
            "note": "Backoff/retry exists; intentional disconnect not forced in Prompt8",
        },
        "terminal_restart": {
            "implemented": True,
            "tested_this_prompt": False,
        },
        "windows_restart": {
            "implemented": "TASK_SCRIPT_PROVIDED",
            "tested_this_prompt": False,
            "reboot_recovery_claimed": False,
        },
        "network_interruption": {
            "implemented": True,
            "tested_this_prompt": False,
        },
        "market_closure": {
            "implemented": True,
            "tested_this_prompt": False,
            "note": "Session schedule aware; market-closed ≠ failure",
        },
        "journal_recovery": {
            "implemented": True,
            "tested_this_prompt": True,
            "note": "Append-only journal + rebuild-index CLI",
        },
        "single_instance_enforcement": {
            "implemented": True,
            "tested_this_prompt": True,
            "currently_blocked_second_start": bool(inst.get("blocked")),
        },
    }

    task_query = _query_windows_task()
    return {
        "health": {
            "service_status": health.get("service_status"),
            "pid": health.get("pid"),
            "pid_alive": health.get("pid_alive"),
            "mt5_connection_state": health.get("mt5_connection_state"),
            "authorizes_execution": health.get("authorizes_execution")
            or (health.get("last_state") or {}).get("authorizes_execution"),
        },
        "single_instance": inst,
        "paths": {
            "pid": str(PID_PATH),
            "state": str(STATE_PATH),
            "log": str(LOG_PATH),
            "journal": str(JOURNAL_ROOT),
            "service_dir": str(SERVICE_DIR),
        },
        "state_totals": state.get("totals"),
        "log_tail": log_tail,
        "capabilities": capabilities,
        "windows_autostart": {
            "task_name": WINDOWS_TASK_NAME,
            "script_path": str(WINDOWS_TASK_SCRIPT),
            "installed": task_query.get("installed"),
            "query": task_query,
            "reboot_recovery_tested": False,
            "reboot_recovery_claimed": False,
            "credentials_in_task": False,
            "broker_write_permissions": False,
            "note": (
                "If Cursor cannot elevate Task Scheduler, run the provided PowerShell script "
                "as Administrator and verify with schtasks /Query."
            ),
        },
        "python_interpreter_expected": str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"),
        "working_directory_expected": str(PROJECT_ROOT),
    }


def _query_windows_task() -> dict[str, Any]:
    if sys.platform != "win32":
        return {"installed": False, "reason": "not_windows"}
    try:
        proc = subprocess.run(
            ["schtasks", "/Query", "/TN", WINDOWS_TASK_NAME, "/V", "/FO", "LIST"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        installed = proc.returncode == 0 and WINDOWS_TASK_NAME.lower() in (proc.stdout or "").lower()
        return {
            "installed": installed,
            "returncode": proc.returncode,
            "stdout_head": (proc.stdout or "")[:500],
            "stderr_head": (proc.stderr or "")[:300],
        }
    except Exception as exc:  # noqa: BLE001
        return {"installed": False, "error": str(exc)}


def write_autostart_script() -> Path:
    """Write install/uninstall/verify commands — does not claim reboot success."""
    WINDOWS_TASK_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    py = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    content = f"""# AIBOT Phase67 read-only collector — Windows Task Scheduler helper
# NO credentials. NO broker writes. NO order_send.
# Reboot recovery is NOT claimed until you reboot and verify.
param(
  [ValidateSet("install","uninstall","verify","help")]
  [string]$Action = "help"
)

$ErrorActionPreference = "Stop"
$TaskName = "{WINDOWS_TASK_NAME}"
$ProjectRoot = "{PROJECT_ROOT}"
$Python = "{py}"
$WorkDir = $ProjectRoot

function Install-AibotCollectorTask {{
    if (-not (Test-Path $Python)) {{ throw "Python not found: $Python" }}
    schtasks /Query /TN $TaskName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {{
        schtasks /Delete /TN $TaskName /F | Out-Null
    }}
    $tr = "`"$Python`" -m phase67.cli start --interval 30 --m5-lookback 50"
    # ONSTART with delay; current user interactive. Credentials are not embedded in this file.
    schtasks /Create /TN $TaskName /SC ONSTART /DELAY 0002:00 /RL LIMITED /RU "$env:USERNAME" /IT /TR $tr /F
    if ($LASTEXITCODE -ne 0) {{ throw "schtasks create failed: $LASTEXITCODE" }}
    Write-Host "Installed $TaskName. Verify with: schtasks /Query /TN $TaskName /V /FO LIST"
    Write-Host "IMPORTANT: Reboot recovery is UNTESTED until you reboot and confirm collector health."
}}

function Uninstall-AibotCollectorTask {{
    schtasks /Delete /TN $TaskName /F
}}

function Verify-AibotCollectorTask {{
    schtasks /Query /TN $TaskName /V /FO LIST
    Set-Location $WorkDir
    $env:PYTHONPATH = Join-Path $WorkDir "src"
    & $Python -m phase67.cli health
}}

switch ($Action) {{
  "install"   {{ Install-AibotCollectorTask }}
  "uninstall" {{ Uninstall-AibotCollectorTask }}
  "verify"    {{ Verify-AibotCollectorTask }}
  default {{
    Write-Host "Actions: install | uninstall | verify"
    Write-Host "Example: powershell -ExecutionPolicy Bypass -File .\\scripts\\install_collector_autostart.ps1 -Action install"
  }}
}}
"""
    WINDOWS_TASK_SCRIPT.write_text(content, encoding="utf-8")
    return WINDOWS_TASK_SCRIPT
