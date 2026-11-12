"""Prompt 10 — final AIBOT delivery. No Prompt 11. No strategy invention."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from signal_bot.execution_economics.collector_reliability import (
    inspect_collector_reliability,
    write_autostart_script,
)
from signal_bot.final_delivery.architecture import build_architecture_audit
from signal_bot.final_delivery.constants import (
    CHAMPION_STATUS,
    DISCORD_ACTIONABLE,
    ENV_OPS_STATUS_LIVE,
    LIVE_TRADING,
    NET_PROFITABILITY,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    PROMPT09_VERDICT,
    REPORTS,
    STRATEGY_APPROVAL,
    VERDICT_BLOCKERS,
    VERDICT_DELIVERED,
    VERDICT_SAFETY,
)
from signal_bot.final_delivery.ops_status import (
    build_ops_snapshot_from_health,
    publish_operational_status,
)
from signal_bot.final_delivery.safety_audit import run_safety_audit
from phase67.service import health_check


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    roots = [
        PROJECT_ROOT / "src" / "signal_bot" / "final_delivery" / "tests",
        PROJECT_ROOT / "src" / "signal_bot" / "final_selection" / "tests",
        PROJECT_ROOT / "src" / "signal_bot" / "execution_economics" / "tests",
        PROJECT_ROOT / "src" / "signal_bot" / "orchestrator" / "tests",
        PROJECT_ROOT / "src" / "signal_bot" / "discovery" / "tests",
        PROJECT_ROOT / "src" / "phase54" / "tests",
        PROJECT_ROOT / "src" / "phase56" / "tests",
        PROJECT_ROOT / "src" / "phase66" / "tests",
        PROJECT_ROOT / "src" / "phase67" / "tests",
    ]
    p69 = PROJECT_ROOT / "src" / "phase69" / "tests"
    if p69.is_dir():
        roots.append(p69)
    for root in roots:
        if root.is_dir():
            suite.addTests(loader.discover(str(root), top_level_dir=str(PROJECT_ROOT / "src")))
    runner = unittest.TextTestRunner(verbosity=1, stream=sys.stdout)
    result = runner.run(suite)
    return {
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(getattr(result, "skipped", [])),
        "failure_names": [str(f[0]) for f in result.failures[:30]],
        "error_names": [str(e[0]) for e in result.errors[:30]],
        "commands": [
            ".venv\\Scripts\\python.exe -m signal_bot.final_delivery.run_prompt10",
            ".venv\\Scripts\\python.exe -m unittest discover -s src/signal_bot/final_delivery/tests -t src",
        ],
    }


def choose_verdict(safety: dict[str, Any], arch: dict[str, Any], tests: dict[str, Any]) -> str:
    if not safety.get("audit_pass"):
        return VERDICT_SAFETY
    if not tests.get("ok"):
        return VERDICT_BLOCKERS
    collector_ok = (arch.get("collector_health") or {}).get("service_status") == "RUNNING"
    # Engineering path works; Discord live ops may be unverified → still delivered with blockers doc
    if collector_ok and safety.get("audit_pass"):
        # Discord live not required for OPERATIONAL_SHADOW if shadow path verified
        return VERDICT_DELIVERED
    return VERDICT_BLOCKERS


def build_bundle() -> dict[str, Any]:
    script = write_autostart_script()
    arch = build_architecture_audit()
    safety = run_safety_audit()
    reliability = inspect_collector_reliability()
    health = health_check()
    snap = build_ops_snapshot_from_health(health, event="PROMPT10_AUDIT")
    ops = publish_operational_status(snap, force_shadow=True)

    blockers = [
        "NO_QUALIFIED_STRATEGY — no champion to publish",
        "Champion NO_MODEL",
        "Strategy approval NOT_APPROVED",
        "NET_PROFITABILITY NOT_ESTABLISHED",
        "Risk policy UNAPPROVED",
        "Discord actionable BUY/SELL DISABLED",
        "0 complete independent Asia+London live dates",
        "Commission UNKNOWN; swap CONFLICTED",
        "Windows reboot recovery UNTESTED",
    ]
    if not arch.get("discord_webhook_configured"):
        blockers.append(
            f"Discord webhook not configured — live ops status blocked "
            f"(set DISCORD_WEBHOOK_URL; optional {ENV_OPS_STATUS_LIVE}=1)"
        )
    else:
        blockers.append(
            f"Discord webhook configured but live ops status not verified in this run "
            f"(shadow recorded; set {ENV_OPS_STATUS_LIVE}=1 to attempt live SYSTEM_STATUS only)"
        )

    return {
        "generated_utc": _utc(),
        "prompt": "PROMPT_10",
        "architecture": arch,
        "safety": safety,
        "collector_reliability": reliability,
        "ops_status_shadow": ops,
        "autostart_script": str(script),
        "blockers": blockers,
        "four_statuses": arch.get("four_statuses"),
        "answers": {
            "read_only_monitoring_operational": (arch.get("collector_health") or {}).get("service_status")
            == "RUNNING",
            "discord_operational_reporting_verified": ops.get("status") == "SENT",
            "discord_ops_status_this_run": ops.get("status"),
            "profitable_strategy_independently_validated": False,
            "actionable_buy_sell_alerts_can_be_enabled": False,
            "broker_execution_authorized": False,
        },
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "prompt09_verdict": PROMPT09_VERDICT,
        "order_send": ORDER_SEND,
        "prompt11_started": False,
    }


def write_ops_md() -> Path:
    path = PROJECT_ROOT / "AIBOT_OPERATIONS.md"
    body = f"""# AIBOT Operations (Final)

**Posture:** Champion `{CHAMPION_STATUS}` · Production `{PRODUCTION_FINAL_ACTION}` · Prompt9 `{PROMPT09_VERDICT}`

This is a **read-only monitoring + shadow-decision** system. It is **not** a profitable production trading bot.

## Start the collector

```powershell
cd C:\\Users\\Dell\\Documents\\1\\AIBOT
$env:PYTHONPATH = "$PWD\\src"
.\\.venv\\Scripts\\python.exe -m phase67.cli start --interval 30
```

## Health check

```powershell
$env:PYTHONPATH = "$PWD\\src"
.\\.venv\\Scripts\\python.exe -m phase67.cli health
```

## Latest evidence

```powershell
.\\.venv\\Scripts\\python.exe -m phase67.cli evidence
.\\.venv\\Scripts\\python.exe -m phase67.cli report
```

## Inspect decisions (orchestrator)

```powershell
.\\.venv\\Scripts\\python.exe -m signal_bot.orchestrator.cli health
.\\.venv\\Scripts\\python.exe -m signal_bot.orchestrator.cli shadow-report
```

## Discord operational reporting

- Default: **SHADOW** (local delivery ledger only; no network).
- Actionable BUY/SELL: **DISABLED** (hard-blocked).
- Optional live **SYSTEM_STATUS** only (never trade alerts):

```powershell
# Requires DISCORD_WEBHOOK_URL in environment or .env (never commit secrets)
$env:AIBOT_DISCORD_OPS_STATUS_LIVE = "1"
$env:PYTHONPATH = "$PWD\\src"
.\\.venv\\Scripts\\python.exe -c "from phase67.service import health_check; from signal_bot.final_delivery.ops_status import build_ops_snapshot_from_health, publish_operational_status; print(publish_operational_status(build_ops_snapshot_from_health(health_check(), event='MANUAL'), force_shadow=False))"
```

A message is **SENT** only if Discord returns HTTP 2xx. Shadow recordings are not claimed as sent.

## Stop the collector

```powershell
.\\.venv\\Scripts\\python.exe -m phase67.cli stop
```

## What WAIT means

NullPolicy / production decision is **WAIT**: no BUY/SELL recommendation. The bot abstains because there is **no qualified strategy**.

## Why actionable trading signals are disabled

- Prompt9 verdict: `{PROMPT09_VERDICT}`
- Strategy approval: `{STRATEGY_APPROVAL}`
- Net profitability: `{NET_PROFITABILITY}`
- Risk policy: UNAPPROVED
- Hard safety lock blocks BUY/SELL Discord and `order_send`

## Before strategy activation (future, outside this 10-prompt plan)

1. Evidence-derived frozen strategy rules
2. ≥20 independent complete Exness Asia+London live dates
3. Date-blocked confirmatory validation beating WAIT
4. Cost model with established net profitability (commission/swap/slippage resolved)
5. Risk policy APPROVED
6. Explicit publication authorization
7. Champion registry update (not via env bypass)

## Windows autostart (optional; reboot UNTESTED)

```powershell
powershell -ExecutionPolicy Bypass -File .\\scripts\\install_collector_autostart.ps1 -Action install
powershell -ExecutionPolicy Bypass -File .\\scripts\\install_collector_autostart.ps1 -Action verify
```

## Safety invariants

- Broker collection: READ_ONLY
- order_send: PROHIBITED
- Live trading: {LIVE_TRADING}
- Discord actionable: {DISCORD_ACTIONABLE}
"""
    _write(path, body)
    return path


def write_reports(bundle: dict[str, Any], tests: dict[str, Any], verdict: str) -> list[str]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    _json(REPORTS / "PROMPT_10_BUNDLE.json", {**bundle, "primary_verdict": verdict, "test_results": tests})
    created.append(str(REPORTS / "PROMPT_10_BUNDLE.json"))

    arch = bundle["architecture"]
    safety = bundle["safety"]
    rel = bundle["collector_reliability"]
    ops = bundle["ops_status_shadow"]
    ans = bundle["answers"]

    docs = {
        "PROMPT_10_FINAL_ARCHITECTURE_AUDIT.md": "\n".join(
            [
                "# PROMPT 10 — Final Architecture Audit",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                f"Primary verdict: `{verdict}`",
                "",
                "## Four statuses",
                "",
                "```json",
                json.dumps(arch.get("four_statuses"), indent=2),
                "```",
                "",
                "## Operational path",
                "",
                "```json",
                json.dumps(arch.get("operational_path"), indent=2),
                "```",
                "",
                "## Live evidence snapshot",
                "",
                "```json",
                json.dumps(arch.get("live_vs_backfill"), indent=2),
                "```",
                "",
                "## Collector / orchestrator",
                "",
                "```json",
                json.dumps(
                    {
                        "collector": arch.get("collector_health"),
                        "single_instance": arch.get("single_instance"),
                        "orchestrator": arch.get("orchestrator_health"),
                    },
                    indent=2,
                ),
                "```",
                "",
            ]
        ),
        "PROMPT_10_DISCORD_OPERATIONS.md": "\n".join(
            [
                "# PROMPT 10 — Discord Operations",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "- Actionable BUY/SELL: **DISABLED** (hard-blocked)",
                "- WAIT never formatted as a trade call",
                "- Webhook secrets not logged; config status only",
                "",
                "## This-run ops status publication",
                "",
                "```json",
                json.dumps(ops, indent=2),
                "```",
                "",
                f"- Live Discord ops verified this run: `{ans.get('discord_operational_reporting_verified')}`",
                f"- Webhook configured (presence only): `{arch.get('discord_webhook_configured')}`",
                "",
                "Live SYSTEM_STATUS requires `DISCORD_WEBHOOK_URL` + "
                f"`{ENV_OPS_STATUS_LIVE}=1`. Trade alerts cannot be emitted via this path.",
                "",
            ]
        ),
        "PROMPT_10_COLLECTOR_DEPLOYMENT.md": "\n".join(
            [
                "# PROMPT 10 — Collector Deployment",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "## Health",
                "",
                "```json",
                json.dumps(rel.get("health"), indent=2),
                "```",
                "",
                "## Windows autostart",
                "",
                "```json",
                json.dumps(rel.get("windows_autostart"), indent=2),
                "```",
                "",
                f"Script: `{bundle.get('autostart_script')}`",
                "",
                "**Reboot recovery is NOT claimed.**",
                "",
                "## Commands",
                "",
                "```powershell",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli start --interval 30",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli health",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli stop",
                "```",
                "",
            ]
        ),
        "PROMPT_10_SAFETY_AUDIT.md": "\n".join(
            [
                "# PROMPT 10 — Safety Audit",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                f"Audit pass: `{safety.get('audit_pass')}`",
                "",
                "```json",
                json.dumps(safety, indent=2),
                "```",
                "",
            ]
        ),
        "PROMPT_10_TEST_RESULTS.md": "\n".join(
            [
                "# PROMPT 10 — Test Results",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "```json",
                json.dumps(tests, indent=2),
                "```",
                "",
            ]
        ),
        "PROMPT_10_FINAL_DELIVERY.md": "\n".join(
            [
                "# PROMPT 10 — Final Delivery",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                f"## Primary verdict: `{verdict}`",
                "",
                "### Separate answers",
                "",
                f"1. Read-only monitoring operational? **{ans.get('read_only_monitoring_operational')}**",
                f"2. Discord operational reporting verified (SENT)? **{ans.get('discord_operational_reporting_verified')}** "
                f"(this run: `{ans.get('discord_ops_status_this_run')}`)",
                f"3. Profitable strategy independently validated? **{ans.get('profitable_strategy_independently_validated')}**",
                f"4. Actionable BUY/SELL can be enabled? **{ans.get('actionable_buy_sell_alerts_can_be_enabled')}**",
                f"5. Broker execution authorized? **{ans.get('broker_execution_authorized')}**",
                "",
                "### Posture",
                "",
                f"- Champion: `{CHAMPION_STATUS}`",
                f"- Production: `{PRODUCTION_FINAL_ACTION}`",
                f"- Prompt9: `{PROMPT09_VERDICT}`",
                f"- order_send: `{ORDER_SEND}`",
                "",
                "This delivery is an **operational shadow bot**, not a profitable trading system.",
                "",
            ]
        ),
        "PROMPT_10_KNOWN_BLOCKERS.md": "\n".join(
            [
                "# PROMPT 10 — Known Blockers",
                "",
                f"Generated: `{bundle['generated_utc']}`",
                "",
                "\n".join(f"- {b}" for b in (bundle.get("blockers") or [])),
                "",
                "No further prompts in this plan. Future research is outside Prompt1–10.",
                "",
            ]
        ),
    }
    for name, body in docs.items():
        p = REPORTS / name
        _write(p, body)
        created.append(str(p))
    ops_path = write_ops_md()
    created.append(str(ops_path))
    return created


def main() -> int:
    if str(PROJECT_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
    bundle = build_bundle()
    tests = _run_tests()
    verdict = choose_verdict(bundle["safety"], bundle["architecture"], tests)
    bundle["primary_verdict"] = verdict
    files = write_reports(bundle, tests, verdict)
    print(
        json.dumps(
            {
                "primary_verdict": verdict,
                "answers": bundle["answers"],
                "safety_pass": bundle["safety"].get("audit_pass"),
                "tests_ok": tests.get("ok"),
                "tests_run": tests.get("tests_run"),
                "failures": tests.get("failures"),
                "errors": tests.get("errors"),
                "files": files,
            },
            indent=2,
        )
    )
    return 0 if tests.get("ok") and bundle["safety"].get("audit_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
