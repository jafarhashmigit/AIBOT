"""Phase 38 runner — canonical historical data engine (no strategy research)."""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase38.acquisition import acquire_representative_dates
from phase38.connection import close_readonly, open_readonly
from phase38.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    EXPECTED_DIGITS,
    EXPECTED_MT5_BUILD,
    EXPECTED_PACKAGE_VERSION,
    EXPECTED_POINT,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MAX_WALL_SECONDS,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RAW_TICKS_DIR,
    RECIPE_ID,
    REPORTS_DIR,
    SYMBOL,
    TELEGRAM_MESSAGES_SENT,
)
from phase38.coverage import build_coverage_map
from phase38.diagnostics import spread_diagnostics
from phase38.dukascopy_compare import compare_overlap_days
from phase38.independent import inventory_raw_counts, verify_all_manifests
from phase38.inventory import build_phase37_inventory
from phase38.progress import write_json
from phase38.qualification import decide_verdict
from phase38.safety import audit_phase38
from phase38.storage import load_jsonl

UTC = timezone.utc


def _write_docs(final: dict[str, Any], runtime: dict[str, Any]) -> None:
    docs = PROJECT_ROOT / "docs" / "agent"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "PHASE_38_RESEARCH_PLAN.md").write_text(
        "\n".join(
            [
                "# Phase 38 — Research Plan",
                "",
                "Canonical historical data engine using Phase37-qualified MT5 source.",
                "Data infrastructure only — no strategy research or edge claims.",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "PHASE_38_RESULTS.md").write_text(
        "\n".join(
            [
                "# Phase 38 — Results",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                f"**Final verdict:** `{final.get('final_verdict')}`",
                f"**M5 records:** `{final.get('m5_record_count')}` | **Tick records:** `{final.get('tick_record_count')}`",
                f"**First/Last verified:** `{final.get('first_verified_timestamp')}` → `{final.get('last_verified_timestamp')}`",
                f"**Production:** `{PRODUCTION_FINAL_ACTION}` | **Champion:** `{CHAMPION_STATUS}`",
                "",
                f"- START_UTC: `{runtime['START_UTC']}`",
                f"- END_UTC: `{runtime['END_UTC']}`",
                f"- DURATION: `{runtime['DURATION']}`",
                "",
                "See `reports/phase38/PHASE38_FINAL_REPORT.md`.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "PHASE_38_DATA_ARCHITECTURE.md").write_text(
        "\n".join(
            [
                "# Phase 38 — Data Architecture",
                "",
                "## Layout",
                "",
                "- `src/data/phase38/mt5/raw/m5/` — immutable raw M5 chunks",
                "- `src/data/phase38/mt5/raw/ticks/` — immutable raw tick chunks",
                "- `src/data/phase38/mt5/canonical/` — canonical copies (separate from raw)",
                "- `src/data/phase38/manifests/` — retrieval manifests + SHA-256",
                "- `src/data/phase38/rejected/` — rejected records with reasons",
                "- `src/data/phase38/state/acquisition_state.json` — resumable state",
                "",
                "## Source limitations",
                "",
                "- Server: MetaQuotes-Demo — **not** live broker execution truth.",
                "- Spreads describe demo feed only.",
                "- Liquid-hour tick samples ≠ full-day coverage.",
                "",
                "## UTC",
                "",
                "All internal timestamps are UTC-aware via `datetime.fromtimestamp(..., tz=UTC)`.",
                "Windows/Pakistan local time is never used for storage.",
                "",
                "## Resume",
                "",
                "```",
                "PYTHONPATH=src python -m phase38.run_phase38",
                "```",
                "",
                "Completed chunks are skipped; checksums verified before reuse.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _final_report_md(final: dict[str, Any], runtime: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 38 — Final Report",
            "",
            f"**Verdict:** `{final.get('final_verdict')}`",
            f"**Reason:** {final.get('verdict_reason')}",
            "",
            "## 1. Implementation summary",
            "Canonical MT5 historical archive with coverage mapping, bounded acquisition,",
            "immutable chunks, manifests/SHA-256, independent reload, and Dukascopy overlap compare.",
            "",
            "## 2. Phase37 artifact inventory",
            "See `reports/phase38/phase37_inventory.json` (paths + SHA-256).",
            "",
            "## 3–6. Coverage / counts / timestamps",
            f"- Completed representative dates: `{final.get('completed_days')}`",
            f"- Pending: `{final.get('pending_days')}`",
            f"- M5 records: `{final.get('m5_record_count')}`",
            f"- Tick records: `{final.get('tick_record_count')}`",
            f"- First verified: `{final.get('first_verified_timestamp')}`",
            f"- Last verified: `{final.get('last_verified_timestamp')}`",
            "Coverage map: `coverage_map.json`",
            "",
            "## 7–9. Quality / spreads / validation",
            "See `acquisition.json`, `spread_diagnostics.json`, `independent_verification.json`.",
            "",
            "## 10–12. Manifests / independent reload / Dukascopy",
            f"- Independent OK: `{final.get('independent_reload_ok')}`",
            f"- Dukascopy compare possible: `{final.get('dukascopy_compare_possible')}`",
            "",
            "## 13. Runtime",
            f"- `{runtime.get('DURATION')}` ({runtime.get('START_UTC')} → {runtime.get('END_UTC')})",
            f"- Stop reason: `{final.get('stop_reason')}`",
            "",
            "## 14. Known limitations",
            "- MetaQuotes-Demo ≠ live broker.",
            "- Tick archives are liquid-hour windows, not full days.",
            "- Coverage probes do not prove unprobed dates.",
            "- No strategy edge claimed.",
            "",
            "## 15. Resume command",
            "```",
            "PYTHONPATH=src python -m phase38.run_phase38",
            "```",
            "",
            "## Safety",
            f"- Champion: `{CHAMPION_STATUS}` | Production: `{PRODUCTION_FINAL_ACTION}`",
            f"- Orders/Discord/Telegram/packages/holdout/commit/push: "
            f"`{BROKER_ORDERS}` / `{DISCORD_MESSAGES_SENT}` / `{TELEGRAM_MESSAGES_SENT}` / "
            f"`{PACKAGES_INSTALLED}` / `{HOLDOUT_ACCESSES}` / `{GIT_COMMIT}` / `{GIT_PUSH}`",
            "",
        ]
    )


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    wall_deadline = time.monotonic() + MAX_WALL_SECONDS

    inventory = build_phase37_inventory()
    safety = audit_phase38()
    write_json("safety_audit.json", safety)

    conn = open_readonly()
    handle = conn.get("handle")
    write_json(
        "preflight.json",
        {
            k: v
            for k, v in {
                **{kk: vv for kk, vv in conn.items() if kk != "handle"},
                "expected_package_version": EXPECTED_PACKAGE_VERSION,
                "expected_build": EXPECTED_MT5_BUILD,
                "expected_digits": EXPECTED_DIGITS,
                "expected_point": EXPECTED_POINT,
                "package_match": str(conn.get("package_version")) == EXPECTED_PACKAGE_VERSION,
                "build_match": conn.get("terminal_build") == EXPECTED_MT5_BUILD,
                "symbol": SYMBOL,
            }.items()
        },
    )

    coverage: dict[str, Any] = {}
    acquisition: dict[str, Any] = {"completed_days": [], "pending_days": [], "results": []}
    spreads: dict[str, Any] = {}
    indep: dict[str, Any] = {"ok": False}
    counts: dict[str, Any] = {}
    duka: dict[str, Any] = {"possible": False}
    stop_reason = None

    try:
        if handle is None:
            stop_reason = conn.get("reason") or "mt5_unavailable"
        else:
            # Reserve ~40% wall for coverage probes, rest for acquisition
            cov_deadline = min(wall_deadline, time.monotonic() + MAX_WALL_SECONDS * 0.4)
            coverage = build_coverage_map(handle, wall_deadline=cov_deadline)
            write_json("coverage_map.json", coverage)

            acquisition = acquire_representative_dates(
                handle,
                server=conn.get("server"),
                terminal_build=conn.get("terminal_build"),
                wall_deadline=wall_deadline,
            )
            write_json("acquisition.json", acquisition)
            stop_reason = acquisition.get("stop_reason")

            # diagnostics from all acquired tick files
            all_ticks: list[dict[str, Any]] = []
            if RAW_TICKS_DIR.exists():
                for p in sorted(RAW_TICKS_DIR.glob("*.jsonl")):
                    all_ticks.extend(load_jsonl(p))
            spreads = spread_diagnostics(all_ticks)
            write_json("spread_diagnostics.json", spreads)
    except Exception as exc:  # noqa: BLE001
        stop_reason = f"exception: {type(exc).__name__}: {exc}"
        write_json("runner_error.json", {"error": stop_reason, "trace": traceback.format_exc()})
    finally:
        close_readonly(handle)

    indep = verify_all_manifests()
    write_json("independent_verification.json", indep)
    counts = inventory_raw_counts()
    write_json("raw_inventory.json", counts)
    duka = compare_overlap_days()
    write_json("dukascopy_compare.json", duka)

    evidence = {
        "connection": {k: v for k, v in conn.items() if k != "handle"},
        "coverage": coverage,
        "acquisition": acquisition,
        "independent": indep,
        "counts": counts,
        "safety": safety,
        "inventory": inventory,
    }
    gates = decide_verdict(evidence)
    write_json("qualification.json", gates)

    end = datetime.now(UTC)
    runtime = {
        "START_UTC": start_s,
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": (end - start).total_seconds(),
        "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
        "wall_budget_s": MAX_WALL_SECONDS,
        "stop_reason": stop_reason,
    }
    write_json("runtime.json", runtime)

    # tests placeholder filled after unittest in shell
    tests = {"ran": False}

    final = {
        "phase": 38,
        "recipe_id": RECIPE_ID,
        "final_verdict": gates["final_verdict"],
        "verdict_reason": gates["reason"],
        "gates": gates["gates"],
        "symbol": SYMBOL,
        "server": conn.get("server"),
        "terminal_build": conn.get("terminal_build"),
        "package_version": conn.get("package_version"),
        "completed_days": acquisition.get("completed_days"),
        "pending_days": acquisition.get("pending_days"),
        "m5_record_count": counts.get("m5_record_count"),
        "tick_record_count": counts.get("tick_record_count"),
        "first_verified_timestamp": counts.get("first_verified_timestamp"),
        "last_verified_timestamp": counts.get("last_verified_timestamp"),
        "independent_reload_ok": indep.get("ok"),
        "dukascopy_compare_possible": duka.get("possible"),
        "spread_overall": spreads.get("overall"),
        "safety_pass": safety.get("pass"),
        "stop_reason": stop_reason,
        "mt5_connections": MT5_CONNECTIONS,
        "broker_orders": BROKER_ORDERS,
        "discord_sent": DISCORD_MESSAGES_SENT > 0,
        "telegram_sent": TELEGRAM_MESSAGES_SENT > 0,
        "packages_installed": PACKAGES_INSTALLED,
        "holdout_accessed": HOLDOUT_ACCESSES > 0,
        "git_commit": GIT_COMMIT,
        "git_push": GIT_PUSH,
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "tests": tests,
        "runtime": runtime,
        "resume_command": "PYTHONPATH=src python -m phase38.run_phase38",
    }
    write_json("final_verdict.json", final)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "PHASE38_FINAL_REPORT.md").write_text(_final_report_md(final, runtime) + "\n", encoding="utf-8")
    _write_docs(final, runtime)
    print(json.dumps({"final_verdict": final["final_verdict"], "completed": final["completed_days"], "runtime": runtime}, indent=2))
    return final


if __name__ == "__main__":
    main()
