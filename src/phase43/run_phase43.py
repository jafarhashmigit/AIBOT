"""Phase 43 runner — independent historical data expansion (no strategy eval)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from phase43.acquisition import acquire_dates
from phase43.connection import close_readonly, open_readonly
from phase43.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MAX_DATES,
    MAX_TICKS_TOTAL,
    MAX_WALL_SECONDS,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
)
from phase43.eligibility import build_eligibility
from phase43.exposure import build_exposure_registry, select_unseen_dates
from phase43.independent import verify_manifests
from phase43.progress import write_json
from phase43.qualification import decide_verdict
from phase43.quality import assess_all

UTC = timezone.utc


def _report(
    *,
    exposure: dict[str, Any],
    selection: dict[str, Any],
    acquisition: dict[str, Any],
    quality: dict[str, Any],
    indep: dict[str, Any],
    eligibility: dict[str, Any],
    verdict: dict[str, Any],
    runtime: dict[str, Any],
) -> str:
    s = exposure.get("summary") or {}
    lines = [
        "# Phase 43 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{verdict.get('final_verdict')}`",
        f"**Reason:** {verdict.get('reason')}",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        "",
        "## 1. Prior exposure audit",
        f"- Window: `{s.get('window_start')}` → `{s.get('window_end')}`",
        f"- Weekdays in window: `{s.get('n_weekdays_in_window')}`",
        f"- UNSEEN: `{s.get('n_unseen')}`",
        f"- PARTIALLY_EXPOSED: `{s.get('n_partially_exposed')}`",
        f"- PREVIOUSLY_EXPOSED: `{s.get('n_previously_exposed')}`",
        f"- UNKNOWN: `{s.get('n_unknown')}`",
        f"- Policy: {s.get('policy')}",
        "Artifact: `prior_exposure_registry.json`",
        "",
        "## 2. Date selection (deterministic, no outcome peeking)",
        f"- Algorithm: {selection.get('algorithm')}",
        f"- Pool UNSEEN: `{selection.get('pool_n')}`",
        f"- Selected: `{selection.get('selected_n')}` → `{selection.get('selected_dates')}`",
        f"- Months: `{selection.get('months_represented')}`",
        "",
        "## 3. Acquisition",
        f"- Completed dates: `{acquisition.get('completed_dates')}`",
        f"- Pending: `{acquisition.get('pending_dates')}`",
        f"- Ticks total: `{acquisition.get('ticks_total')}` / max `{MAX_TICKS_TOTAL}`",
        f"- Stop reason: `{acquisition.get('stop_reason')}`",
        "",
        "## 4. M5 / H1 / tick coverage",
        f"- Complete sessions: `{quality.get('n_complete_sessions')}`",
        f"- H1 warmup ≥30: `{quality.get('n_h1_warmup_ok')}`",
        f"- EMA20 ready: `{quality.get('n_ema20_ready')}`",
        f"- Total ticks: `{quality.get('total_ticks')}`",
        "",
        "## 5. Per-date quality (summary)",
    ]
    for r in quality.get("rows") or []:
        lines.append(
            f"- `{r['day']}`: session=`{r['session_status']}` m5=`{r['m5_n']}` "
            f"h1_warm=`{r['h1_warmup_before_day']}` ticks=`{r['tick_n']}` "
            f"empty_h=`{r['hours_empty']}` missing_h=`{r['hours_missing_file']}` "
            f"spread_med=`{r['spread_median']}` p95=`{r['spread_p95']}` p99=`{r['spread_p99']}`"
        )
    lines += [
        "",
        "## 6. SHA-256 / independent reload",
        f"- OK: `{indep.get('ok')}` manifests=`{indep.get('n_manifests')}` fails=`{indep.get('n_fail')}`",
        "",
        "## 7. Future research eligibility",
        f"- A truly unseen ready: n=`{eligibility.get('A_n')}` dates=`{eligibility.get('A_truly_unseen_independent_validation_eligible')}`",
        f"- B partial exploratory: n=`{eligibility.get('B_n')}`",
        f"- C previously exposed prohibited: n=`{eligibility.get('C_n')}`",
        f"- Proposed allocation: `{eligibility.get('proposed_chronological_allocation')}`",
        "",
        "## 8. Runtime and limits",
        f"- Duration: `{runtime.get('DURATION')}`",
        f"- Wall budget: `{MAX_WALL_SECONDS}` s | max dates `{MAX_DATES}` | max ticks `{MAX_TICKS_TOTAL}`",
        "",
        "## 9. Limitations",
        "- Independence is relative to Phases 0–42 artifact audit; UNKNOWN residual risk remains if undocumented human inspection occurred.",
        "- MetaQuotes-Demo history ≠ live broker.",
        "- No strategy/hypothesis evaluation performed in this phase.",
        "- H1 neighbor days of prior eval dates classified PARTIALLY_EXPOSED and excluded from independent set.",
        "",
        "## Safety",
        "- No Phase0–42 modifications; no commits/pushes; no broker orders; no packages; no holdout; no signals.",
        f"- Counters orders/Discord/Telegram/packages/holdout/commit/push/mt5 = "
        f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
        f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}/{MT5_CONNECTIONS}",
        "",
    ]
    return "\n".join(lines)


def _docs(verdict: dict[str, Any]) -> None:
    docs = PROJECT_ROOT / "docs" / "agent"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "PHASE_43_RESEARCH_PLAN.md").write_text(
        "\n".join(
            [
                "# Phase 43 — Research Plan",
                "",
                "Expand XAUUSD historical archives with genuinely UNSEEN dates for future independent validation.",
                "Data qualification only — no strategy or hypothesis scoring.",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "PHASE_43_RESULTS.md").write_text(
        "\n".join(
            [
                "# Phase 43 — Results",
                "",
                f"**Verdict:** `{verdict.get('final_verdict')}`",
                f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                "See `reports/phase43/PHASE43_FINAL_REPORT.md`.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    wall_deadline = time.monotonic() + MAX_WALL_SECONDS

    exposure = build_exposure_registry()
    selection = select_unseen_dates(exposure, k=MAX_DATES)
    selected = selection.get("selected_dates") or []

    conn = open_readonly()
    handle = conn.get("handle")
    write_json("preflight.json", {k: v for k, v in conn.items() if k != "handle"})

    acquisition: dict[str, Any] = {
        "completed_dates": [],
        "pending_dates": selected,
        "ticks_total": 0,
        "stop_reason": None,
        "results": [],
    }
    try:
        if handle is None:
            acquisition["stop_reason"] = conn.get("reason") or "mt5_unavailable"
        elif not selected:
            acquisition["stop_reason"] = "no_unseen_dates_selected"
        else:
            acquisition = acquire_dates(
                handle,
                selected,
                server=conn.get("server"),
                terminal_build=conn.get("terminal_build"),
                wall_deadline=wall_deadline,
            )
    finally:
        close_readonly(handle)

    write_json("acquisition.json", acquisition)

    quality_days = sorted(set(acquisition.get("completed_dates") or []) | set(selected))
    # assess only dates with any files / completed
    quality = assess_all(list(acquisition.get("completed_dates") or []))
    write_json("quality_report.json", quality)

    indep = verify_manifests()
    write_json("independent_verification.json", indep)

    eligibility = build_eligibility(
        exposure=exposure,
        selection=selection,
        quality=quality,
        acquisition=acquisition,
    )

    verdict = decide_verdict(
        exposure=exposure,
        selection=selection,
        acquisition=acquisition,
        quality=quality,
        indep_ok=bool(indep.get("ok")),
        eligibility=eligibility,
    )
    write_json("qualification.json", verdict)

    end = datetime.now(UTC)
    runtime = {
        "START_UTC": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": (end - start).total_seconds(),
        "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
        "wall_budget_s": MAX_WALL_SECONDS,
        "stop_reason": acquisition.get("stop_reason"),
    }
    write_json("runtime.json", runtime)

    final = {
        "phase": 43,
        "recipe_id": RECIPE_ID,
        "final_verdict": verdict.get("final_verdict"),
        "verdict_reason": verdict.get("reason"),
        "n_unseen_pool": (exposure.get("summary") or {}).get("n_unseen"),
        "n_selected": selection.get("selected_n"),
        "n_acquired_complete": len(acquisition.get("completed_dates") or []),
        "n_independent_ready": eligibility.get("A_n"),
        "ticks_total": acquisition.get("ticks_total"),
        "independent_ok": indep.get("ok"),
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "no_strategy_evaluation": True,
        "no_hypothesis_scoring": True,
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)
    (REPORTS_DIR / "PHASE43_FINAL_REPORT.md").write_text(
        _report(
            exposure=exposure,
            selection=selection,
            acquisition=acquisition,
            quality=quality,
            indep=indep,
            eligibility=eligibility,
            verdict=verdict,
            runtime=runtime,
        )
        + "\n",
        encoding="utf-8",
    )
    _docs(verdict)
    print(json.dumps(final, indent=2))
    return final


if __name__ == "__main__":
    main()
