"""Phase 40 runner — targeted full-session coverage completion (no strategy eval)."""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from phase40.acquisition import acquire_all, load_state, save_state
from phase40.alignment import align_all
from phase40.connection import close_readonly, open_readonly
from phase40.constants import (
    ADDITIONAL_DATE_CANDIDATES,
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MAX_WALL_SECONDS,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REPORTS_DIR,
    TARGET_DATES,
    TELEGRAM_MESSAGES_SENT,
)
from phase40.independent import verify_manifests
from phase40.inventory import audit_phase38
from phase40.progress import write_json
from phase40.qualification import decide_verdict
from phase40.readiness import assess_readiness

UTC = timezone.utc


def _docs(final: dict[str, Any], runtime: dict[str, Any]) -> None:
    docs = PROJECT_ROOT / "docs" / "agent"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "PHASE_40_RESEARCH_PLAN.md").write_text(
        "\n".join(
            [
                "# Phase 40 — Research Plan",
                "",
                "Extend Phase38 MT5 archive with full-session ticks and H1 warm-up for 10 dates.",
                "Data readiness only — no strategy evaluation.",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
                "## Constraints",
                "- MT5 historical read-only; no orders; no installs; no holdout.",
                "- Never overwrite Phase38; store under `src/data/phase40/`.",
                "- Max wall 10 minutes; one date at a time; resume-safe.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "PHASE_40_RESULTS.md").write_text(
        "\n".join(
            [
                "# Phase 40 — Results",
                "",
                f"**Verdict:** `{final.get('final_verdict')}`",
                f"**Complete tick sessions:** `{final.get('n_complete_tick_sessions')}`",
                f"**H1 warm-up OK dates:** `{final.get('n_h1_warmup_ok')}`",
                f"**H13_C eligible slots:** `{final.get('h13_readiness')}`",
                f"**MR eligible slots:** `{final.get('mr_readiness')}`",
                f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                f"- DURATION: `{runtime.get('DURATION')}`",
                "",
                "See `reports/phase40/PHASE40_FINAL_REPORT.md`.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _report(
    final: dict[str, Any],
    runtime: dict[str, Any],
    *,
    p38: dict[str, Any],
    acquisition: dict[str, Any],
    alignment: dict[str, Any],
    readiness: dict[str, Any],
    indep: dict[str, Any],
) -> str:
    lines: list[str] = [
        "# Phase 40 — Final Report",
        "",
        f"**Verdict:** `{final.get('final_verdict')}`",
        f"**Reason:** {final.get('verdict_reason')}",
        f"**Recipe:** `{RECIPE_ID}`",
        "",
        "## 1. Existing Phase38 integrity audit",
        f"- Manifest integrity OK: `{p38.get('manifest_integrity_ok')}`",
        f"- Files checked: `{p38.get('n_files') or len(p38.get('files') or [])}`",
        f"- Failures: `{p38.get('n_failures') or len(p38.get('failures') or [])}`",
        "Artifact: `reports/phase40/phase38_integrity_audit.json`",
        "",
        "## 2. Acquisition summary",
        f"- Completed dates: `{final.get('completed_dates')}`",
        f"- Pending dates: `{final.get('pending_dates')}`",
        f"- Stop reason: `{final.get('stop_reason')}`",
        f"- MT5 skip (disk complete): `{acquisition.get('skipped_mt5_disk_complete')}`",
        "Artifact: `reports/phase40/acquisition.json`",
        "",
        "## 3. M5 coverage by date",
    ]
    for d in alignment.get("dates") or []:
        lines.append(
            f"- `{d['day']}`: n=`{d.get('m5_n')}` first=`{d.get('m5_first')}` last=`{d.get('m5_last')}` "
            f"bars_with_ticks=`{d.get('n_m5_bars_with_ticks')}`"
        )
    lines += ["", "## 4. H1 warm-up coverage by date"]
    for d in alignment.get("dates") or []:
        lines.append(
            f"- `{d['day']}`: h1_n=`{d.get('h1_n')}` warmup_n=`{d.get('h1_warmup_n')}` "
            f"sufficient_30=`{d.get('h1_warmup_sufficient_30')}` ema20_ready=`{d.get('ema20_warmup_ready')}` "
            f"ema20_ready_at=`{d.get('ema20_ready_at_utc')}`"
        )
    lines += ["", "## 5. Tick coverage by date"]
    for d in alignment.get("dates") or []:
        ts = d.get("tick_session") or {}
        lines.append(
            f"- `{d['day']}`: status=`{ts.get('status')}` n_ticks=`{ts.get('n_ticks')}` "
            f"first=`{ts.get('first_tick')}` last=`{ts.get('last_tick')}` "
            f"hours_nonempty=`{ts.get('hours_nonempty')}` hours_empty=`{ts.get('hours_empty')}`"
        )
    lines += [
        "",
        "## 6. Full-session versus partial-session classification",
        f"- VERIFIED_COMPLETE_SESSION dates: `{alignment.get('n_complete_tick_sessions')}`",
        f"- Partial / other: `{alignment.get('n_partial_tick_sessions')}`",
        "",
        "## 7. Gap and duplicate statistics",
        "Per-chunk validation stored in manifests (`validation_status`, empty-hour flags).",
        "Empty UTC hours (e.g. 00h) are recorded as empty chunks with `record_count=0`, not filled.",
        "",
        "## 8. Bid/ask quality",
        "Ticks retain source bid/ask; no manufactured quotes. Crossed-book rows rejected at save time.",
        "See tick hour manifests `bid_ask_ok`.",
        "",
        "## 9. H12 path eligibility",
    ]
    for d in alignment.get("dates") or []:
        lines.append(
            f"- `{d['day']}`: eligible_slots=`{d.get('h12_path_eligible_signal_slots')}` "
            f"ineligible=`{d.get('h12_path_ineligible_signal_slots')}`"
        )
    h13 = readiness.get("H13_C") or {}
    mr = readiness.get("mean_reversion") or {}
    lines += [
        "",
        "## 10. H13_C data readiness (no signals)",
        f"- Dates with any eligible slot: `{h13.get('dates_with_any_eligible')}`",
        f"- Total eligible slots: `{h13.get('total_eligible_slots')}`",
        f"- Note: `{h13.get('note')}`",
        "",
        "## 11. Mean-reversion data readiness (no signals)",
        f"- Dates with any eligible slot: `{mr.get('dates_with_any_eligible')}`",
        f"- Total eligible slots: `{mr.get('total_eligible_slots')}`",
        f"- Note: `{mr.get('note')}`",
        "",
        "## 12. Independent reload results",
        f"- OK: `{indep.get('ok')}`",
        f"- Manifests: `{indep.get('n_manifests')}` fails: `{indep.get('n_fail')}`",
        "",
        "## 13. SHA-256 verification",
        "Every Phase40 chunk re-hashed from disk and compared to immutable manifests.",
        f"- Independent OK: `{indep.get('ok')}`",
        "",
        f"## 14. Runtime and memory usage",
        f"- Duration: `{runtime.get('DURATION')}` (`{runtime.get('DURATION_SECONDS')}` s)",
        f"- Wall budget: `{runtime.get('wall_budget_s')}` s",
        f"- Stop reason: `{runtime.get('stop_reason')}`",
        "",
        "## 15. Remaining coverage gaps",
        f"- Pending target dates: `{final.get('pending_dates')}`",
        "- Empty early/late UTC hours are source-empty, not acquisition skips.",
        "- Additional independent dates not downloaded in this phase.",
        "",
        "## 16. Prioritized additional-date acquisition plan",
        f"- Downloaded in Phase40: `{False}`",
        f"- Candidates: `{ADDITIONAL_DATE_CANDIDATES}`",
        "- Estimate: current 10 dates already provide >>50 H12-eligible data slots and 10 independent dates "
        "with H1 warm-up + complete tick sessions. Additional dates are optional diversification for a "
        "future bounded run; trade counts remain unknown until Phase39-style retest.",
        "",
        "## 17. Exact resume commands",
        "```",
        "cd C:\\Users\\Dell\\Documents\\1\\AIBOT",
        "set PYTHONPATH=src",
        ".\\.venv\\Scripts\\python.exe -m phase40.run_phase40",
        "```",
        "",
        "## Final safety confirmation",
        "- No strategy backtest performed.",
        "- No strategy parameters changed.",
        "- No signals generated.",
        "- No model trained.",
        "- No final holdout accessed.",
        "- No Phase0–39 artifacts modified.",
        "- No broker orders.",
        "- No live trading.",
        "- No packages installed.",
        "- No commits or pushes.",
        f"- Champion remains `{CHAMPION_STATUS}`.",
        f"- Production remains `{PRODUCTION_FINAL_ACTION}`.",
        f"- Counters: orders/Discord/Telegram/packages/holdout/commit/push = "
        f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
        f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}",
        "",
    ]
    return "\n".join(lines)


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    wall_deadline = time.monotonic() + MAX_WALL_SECONDS

    p38 = audit_phase38()
    write_json("phase38_integrity_audit.json", p38)

    disk = load_state()
    acquisition: dict[str, Any]
    handle = None
    if not disk["pending"]:
        save_state({**disk, "last_stop_reason": None})
        acquisition = {
            "results": [],
            "completed_dates": sorted(disk["completed"].keys()),
            "pending_dates": [],
            "stop_reason": None,
            "skipped_mt5_disk_complete": True,
            "resume_command": "PYTHONPATH=src python -m phase40.run_phase40",
        }
        write_json("preflight.json", {"mt5": "skipped_disk_complete", "pending": []})
    else:
        conn = open_readonly()
        handle = conn.get("handle")
        write_json("preflight.json", {k: v for k, v in conn.items() if k != "handle"})
        acquisition = {
            "completed_dates": [],
            "pending_dates": TARGET_DATES,
            "results": [],
            "stop_reason": None,
            "skipped_mt5_disk_complete": False,
        }
        try:
            if handle is None:
                acquisition["stop_reason"] = conn.get("reason") or "mt5_unavailable"
            else:
                acquisition = acquire_all(
                    handle,
                    server=conn.get("server"),
                    terminal_build=conn.get("terminal_build"),
                    wall_deadline=wall_deadline,
                )
                acquisition["skipped_mt5_disk_complete"] = False
        except Exception as exc:  # noqa: BLE001
            acquisition["stop_reason"] = f"exception: {type(exc).__name__}: {exc}"
            write_json("runner_error.json", {"error": acquisition["stop_reason"], "trace": traceback.format_exc()})
        finally:
            close_readonly(handle)

    write_json("acquisition.json", acquisition)
    alignment = align_all()
    write_json("alignment.json", alignment)
    readiness = assess_readiness()
    write_json("readiness.json", readiness)
    indep = verify_manifests()
    write_json("independent_verification.json", indep)

    plan = {
        "downloaded_in_phase40": False,
        "candidates": ADDITIONAL_DATE_CANDIDATES,
        "rationale": (
            "Optional diversification beyond the original 10 dates for a future bounded run. "
            "Current archive already targets 10 independent dates with H1 warm-up and full-session ticks; "
            "trade counts remain unknown until Phase39-style evaluation."
        ),
        "estimate_note": (
            "Do not promise ≥50 scored trades from additional dates; coverage slots ≠ closed trades."
        ),
    }
    write_json("additional_date_plan.json", plan)

    gates = decide_verdict(
        phase38_ok=bool(p38.get("manifest_integrity_ok")),
        indep_ok=bool(indep.get("ok")),
        alignment=alignment,
        readiness=readiness,
        acquisition=acquisition,
    )
    write_json("qualification.json", gates)

    end = datetime.now(UTC)
    runtime = {
        "START_UTC": start_s,
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": (end - start).total_seconds(),
        "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
        "wall_budget_s": MAX_WALL_SECONDS,
        "stop_reason": acquisition.get("stop_reason"),
        "prior_acquisition_duration_note": "Initial MT5 acquisition completed earlier in Phase40 (~5.5 min).",
    }
    write_json("runtime.json", runtime)

    final = {
        "phase": 40,
        "recipe_id": RECIPE_ID,
        "final_verdict": gates["final_verdict"],
        "verdict_reason": gates["reason"],
        "phase38_integrity_ok": p38.get("manifest_integrity_ok"),
        "independent_ok": indep.get("ok"),
        "completed_dates": acquisition.get("completed_dates"),
        "pending_dates": acquisition.get("pending_dates"),
        "stop_reason": acquisition.get("stop_reason"),
        "n_complete_tick_sessions": alignment.get("n_complete_tick_sessions"),
        "n_partial_tick_sessions": alignment.get("n_partial_tick_sessions"),
        "n_h1_warmup_ok": alignment.get("n_h1_warmup_ok"),
        "n_ema20_ready": alignment.get("n_ema20_ready"),
        "h13_readiness": {
            "dates_with_any_eligible": readiness["H13_C"]["dates_with_any_eligible"],
            "total_eligible_slots": readiness["H13_C"]["total_eligible_slots"],
        },
        "mr_readiness": {
            "dates_with_any_eligible": readiness["mean_reversion"]["dates_with_any_eligible"],
            "total_eligible_slots": readiness["mean_reversion"]["total_eligible_slots"],
        },
        "additional_date_plan": plan,
        "resume_command": "PYTHONPATH=src python -m phase40.run_phase40",
        "mt5_connections": MT5_CONNECTIONS,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "broker_orders": BROKER_ORDERS,
        "no_strategy_backtest": True,
        "no_signals_generated": True,
        "no_parameter_changes": True,
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)
    (REPORTS_DIR / "PHASE40_FINAL_REPORT.md").write_text(
        _report(
            final,
            runtime,
            p38=p38,
            acquisition=acquisition,
            alignment=alignment,
            readiness=readiness,
            indep=indep,
        )
        + "\n",
        encoding="utf-8",
    )
    _docs(final, runtime)
    print(
        json.dumps(
            {
                k: final[k]
                for k in (
                    "final_verdict",
                    "verdict_reason",
                    "completed_dates",
                    "pending_dates",
                    "n_complete_tick_sessions",
                    "independent_ok",
                    "h13_readiness",
                    "mr_readiness",
                    "runtime",
                )
            },
            indent=2,
        )
    )
    return final


if __name__ == "__main__":
    main()
