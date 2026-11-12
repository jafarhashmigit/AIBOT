"""Phase 53 — final bounded costed decision-edge development on XAUUSD/M5."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from phase53.acquisition import acquire_dates, load_state
from phase53.connection import close_readonly, open_readonly
from phase53.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    DOCS_DIR,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MAX_WALL_SECONDS,
    MIN_CONFIRMATION_DATES,
    MIN_DISCOVERY_DATES,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
    canonical_json_sha256,
)
from phase53.date_selection import freeze_date_selection
from phase53.evaluation import run_confirmation, run_discovery
from phase53.events import build_events_for_dates
from phase53.exposure_audit import build_exposure_ledger
from phase53.freeze import freeze_policies
from phase53.independent import recompute_mean
from phase53.policies import family_registry
from phase53.progress import write_json, write_text
from phase53.qualification import choose_verdict


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _docs(verdict: str, reason: str) -> str:
    return f"""# Phase 53 — Final Costed Decision Edge Development

**Recipe:** `{RECIPE_ID}`  
**Verdict:** `{verdict}`  
**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`

{reason}

Substrate: XAUUSD/M5 (Phase52). No Phase50/51 learner revival. No Phase54 started.

See `reports/phase53/FINAL_REPORT.md`.
"""


def _report(p: dict[str, Any]) -> str:
    disc = p.get("discovery") or {}
    conf = p.get("confirmation") or {}
    lines = [
        "# Phase 53 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{p['final_verdict']}`",
        f"**Champion:** `{p['champion']}` | **Production:** `{p['production']}`",
        f"**Reason:** {p.get('verdict_reason')}",
        "",
        "## Exposure audit",
        f"- Eligible unseen dates: `{p.get('eligible_unseen_n')}`",
        f"- Class counts: `{p.get('exposure_class_counts')}`",
        f"- Never-open (Phase44 validation ∪ Phase49 confirmation): `{p.get('never_open_n')}`",
        f"- Phase51 confirmation excluded from fit: yes",
        "",
        "## Date selection",
        f"- Selection SHA: `{p.get('selection_sha256')}`",
        f"- Discovery (`{p.get('n_discovery')}`): `{p.get('discovery_dates')}`",
        f"- Confirmation sealed (`{p.get('n_confirmation')}`): `{p.get('confirmation_dates')}`",
        "",
        "## Acquisition",
        f"- Completed discovery dates: `{p.get('n_disc_completed')}`",
        f"- Completed confirmation dates: `{p.get('n_conf_completed')}`",
        f"- Ticks total: `{p.get('ticks_total')}`",
        f"- Stop reason: `{p.get('acq_stop_reason')}`",
        "",
        "## Hypothesis registry / policy freeze",
        f"- Registry SHA: `{p.get('registry_sha256')}`",
        f"- Policy freeze SHA: `{p.get('policy_freeze_sha256')}`",
        f"- Families: F1_CMC (costed momentum), F2_EXF (exhaustion fade), F3_SLF (session MTF)",
        f"- Horizon: 12 M5 bars; BUY ask→bid / SELL bid→ask; WAIT=0; no invented commission/slippage",
        "",
        "## Discovery",
        f"- Events: `{disc.get('n_events')}`",
        f"- Survivors: `{disc.get('survivors')}` (n=`{disc.get('n_survivors')}`)",
        f"- Per-family gates: `{p.get('discovery_gates')}`",
        "",
        "## Confirmation",
        f"- Opened: `{conf.get('opened')}`",
        f"- Confirmed: `{conf.get('confirmed_ids')}`",
        f"- Fail detail: `{p.get('confirmation_detail')}`",
        "",
        "## Baselines / controls (discovery survivor summary)",
        f"- `{p.get('baseline_snapshot')}`",
        "",
        "## Independent recomputation",
        f"- `{p.get('independent')}`",
        "",
        "## Limitations",
        "- MetaQuotes-Demo bid/ask ≠ live execution",
        "- Demo spreads observed only; commission/slippage not invented",
        "- Phase44 validation and Phase49 confirmation dates never opened",
        "- Not a profitability claim unless verdict is INDEPENDENT_EDGE_CONFIRMED",
        "",
        "## Recommendation",
        f"{p.get('recommendation')}",
        "",
        f"Runtime s: `{p.get('duration_s')}`",
        "",
        "No Phase54 started. Champion remains NO_MODEL unless confirmed.",
    ]
    return "\n".join(lines) + "\n"


def main() -> dict[str, Any]:
    t0 = time.monotonic()
    start = _utc()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    ledger = build_exposure_ledger()
    selection = freeze_date_selection(ledger)
    discovery_dates = list(selection["discovery_dates"])
    confirmation_dates = list(selection["confirmation_dates"])
    all_selected = list(selection["selected_dates"])

    payload: dict[str, Any] = {
        "eligible_unseen_n": ledger.get("eligible_unseen_n"),
        "exposure_class_counts": ledger.get("class_counts"),
        "never_open_n": ledger.get("never_open_dates_n"),
        "selection_sha256": selection.get("selection_sha256"),
        "discovery_dates": discovery_dates,
        "confirmation_dates": confirmation_dates,
        "n_discovery": len(discovery_dates),
        "n_confirmation": len(confirmation_dates),
    }

    if ledger.get("eligible_unseen_n", 0) < (MIN_DISCOVERY_DATES + MIN_CONFIRMATION_DATES):
        payload["insufficient_independent_data"] = (
            f"Only {ledger.get('eligible_unseen_n')} eligible unseen dates remain "
            f"(need ≥{MIN_DISCOVERY_DATES}+{MIN_CONFIRMATION_DATES})."
        )
        verdict, reason = choose_verdict(payload)
        return _finalize(payload, verdict, reason, start, t0, skip_mt5=True)

    reg = family_registry()
    write_json(REPORTS_DIR / "hypothesis_registry.json", reg)
    payload["registry_sha256"] = reg["registry_sha256"]

    # Acquire discovery first; keep confirmation sealed until freeze after discovery
    conn = open_readonly()
    if conn.get("status") != "connected_readonly":
        payload["data_integrity_failure"] = f"MT5 unavailable: {conn.get('reason')}"
        verdict, reason = choose_verdict(payload)
        return _finalize(payload, verdict, reason, start, t0, skip_mt5=True)

    handle = conn["handle"]
    try:
        wall = time.monotonic() + MAX_WALL_SECONDS
        acq_disc = acquire_dates(
            handle,
            discovery_dates,
            server=conn.get("server"),
            terminal_build=conn.get("terminal_build"),
            wall_deadline=wall,
        )
        write_json(REPORTS_DIR / "acquisition_discovery.json", acq_disc)
        disc_completed = list(acq_disc.get("completed_dates") or [])
        payload["n_disc_completed"] = len(disc_completed)
        payload["ticks_total"] = acq_disc.get("ticks_total")
        payload["acq_stop_reason"] = acq_disc.get("stop_reason")

        if len(disc_completed) < MIN_DISCOVERY_DATES:
            payload["insufficient_independent_data"] = (
                f"Only {len(disc_completed)} discovery dates acquired (need ≥{MIN_DISCOVERY_DATES})."
            )
            verdict, reason = choose_verdict(payload)
            return _finalize(payload, verdict, reason, start, t0)

        ev_disc = build_events_for_dates(disc_completed)
        write_json(
            REPORTS_DIR / "events_discovery.json",
            {k: v for k, v in ev_disc.items() if k != "events"},
        )
        if ev_disc.get("overlap_violations", 0) > 0:
            payload["data_integrity_failure"] = f"overlap_violations={ev_disc['overlap_violations']}"
            verdict, reason = choose_verdict(payload)
            return _finalize(payload, verdict, reason, start, t0)

        family_ids = ["F1_CMC", "F2_EXF", "F3_SLF"]
        discovery = run_discovery(ev_disc["events"], family_ids)
        discovery["n_events"] = ev_disc["n_events"]
        write_json(REPORTS_DIR / "discovery_results.json", discovery)
        payload["discovery"] = discovery
        payload["discovery_gates"] = {
            r["family_id"]: r["gate"] for r in discovery.get("results") or []
        }
        payload["baseline_snapshot"] = {
            r["family_id"]: {
                "policy": (r.get("summary") or {}).get("calibration"),
                "baselines": r.get("baselines"),
                "controls": r.get("controls"),
                "gate": r.get("gate"),
            }
            for r in discovery.get("results") or []
        }

        frozen = freeze_policies(discovery)
        payload["policy_freeze_sha256"] = frozen.get("policy_freeze_sha256")

        survivors = list(discovery.get("survivors") or [])
        if not survivors:
            payload["confirmation"] = {"opened": False, "reason": "no_discovery_survivors", "n_confirmed": 0}
            payload["independent"] = []
            payload["recommendation"] = (
                "Stop the current strategy-development approach on this substrate. "
                "No family beat meaningful baselines under costed EV. Do not open another exploratory chain."
            )
            verdict, reason = choose_verdict(payload)
            return _finalize(payload, verdict, reason, start, t0)

        # Acquire confirmation only after freeze (remaining wall + bounded extension)
        rem = max(120.0, wall - time.monotonic())
        acq_conf = acquire_dates(
            handle,
            confirmation_dates,
            server=conn.get("server"),
            terminal_build=conn.get("terminal_build"),
            wall_deadline=time.monotonic() + rem + 900,
        )
        write_json(REPORTS_DIR / "acquisition_confirmation.json", acq_conf)
        conf_completed = list(acq_conf.get("completed_dates") or [])
        payload["n_conf_completed"] = len(conf_completed)
        payload["ticks_total"] = acq_conf.get("ticks_total")
        if acq_conf.get("stop_reason"):
            payload["acq_stop_reason"] = acq_conf.get("stop_reason")

        if len(conf_completed) < MIN_CONFIRMATION_DATES:
            payload["insufficient_independent_data"] = (
                f"Only {len(conf_completed)} confirmation dates acquired (need ≥{MIN_CONFIRMATION_DATES})."
            )
            payload["confirmation"] = {"opened": False, "reason": "insufficient_confirmation_data", "n_confirmed": 0}
            verdict, reason = choose_verdict(payload)
            return _finalize(payload, verdict, reason, start, t0)

        ev_conf = build_events_for_dates(conf_completed)
        write_json(
            REPORTS_DIR / "events_confirmation.json",
            {k: v for k, v in ev_conf.items() if k != "events"},
        )
        confirmation = run_confirmation(
            ev_conf["events"],
            survivors,
            frozen_ood=discovery.get("frozen_ood_bounds") or {},
        )
        write_json(REPORTS_DIR / "confirmation_results.json", confirmation)
        payload["confirmation"] = confirmation
        payload["confirmation_detail"] = {
            r["family_id"]: r.get("confirmation_gate") for r in confirmation.get("results") or []
        }
        payload["independent"] = [
            recompute_mean(ev_conf["events"], fid, discovery.get("frozen_ood_bounds") or {})
            for fid in survivors
        ]
        write_json(REPORTS_DIR / "independent_recompute.json", payload["independent"])

        if confirmation.get("n_confirmed", 0) > 0:
            payload["recommendation"] = (
                "Integrate the confirmed frozen policy as a candidate for guarded offline evaluation only. "
                "Champion stays NO_MODEL until production governance promotes it. Production remains WAIT."
            )
        else:
            payload["recommendation"] = (
                "Independent confirmation failed. Stop the current strategy-development approach; "
                "do not tune failed candidates or auto-start Phase54."
            )

        verdict, reason = choose_verdict(payload)
        return _finalize(payload, verdict, reason, start, t0)
    finally:
        close_readonly(handle)


def _finalize(
    payload: dict[str, Any],
    verdict: str,
    reason: str,
    start: str,
    t0: float,
    *,
    skip_mt5: bool = False,
) -> dict[str, Any]:
    end = _utc()
    # Champion / production safety
    champion = CHAMPION_STATUS
    production = PRODUCTION_FINAL_ACTION
    if verdict == "INDEPENDENT_EDGE_CONFIRMED":
        # Still do not auto-promote production; champion may note candidate but recipe says
        # Champion remains NO_MODEL unless genuinely validated — allow documenting candidate
        # while keeping production WAIT and champion NO_MODEL per safety section.
        champion = CHAMPION_STATUS
        production = PRODUCTION_FINAL_ACTION

    out = {
        **payload,
        "phase": 53,
        "recipe": RECIPE_ID,
        "final_verdict": verdict,
        "verdict_reason": reason,
        "champion": champion,
        "production": production,
        "duration_s": time.monotonic() - t0,
        "runtime": {"START_UTC": start, "END_UTC": end, "DURATION_SECONDS": time.monotonic() - t0},
        "safety": {
            "broker_orders": BROKER_ORDERS,
            "discord": DISCORD_MESSAGES_SENT,
            "telegram": TELEGRAM_MESSAGES_SENT,
            "packages_installed": PACKAGES_INSTALLED,
            "holdout_accesses": HOLDOUT_ACCESSES,
            "git_commit": GIT_COMMIT,
            "git_push": GIT_PUSH,
            "mt5_connections": MT5_CONNECTIONS,
            "skip_mt5": skip_mt5,
        },
    }
    if "recommendation" not in out:
        if verdict == "INSUFFICIENT_INDEPENDENT_DATA":
            out["recommendation"] = (
                "Insufficient independent dates/data for a justified edge claim. Stop; do not fabricate coverage."
            )
        elif verdict == "DATA_INTEGRITY_FAILURE":
            out["recommendation"] = "Resolve data integrity before any further decision-policy work."
        else:
            out["recommendation"] = (
                "No validated costed decision edge. Stop the current strategy-development approach."
            )

    out["artifact_sha256"] = canonical_json_sha256(
        {k: out[k] for k in ("final_verdict", "verdict_reason", "selection_sha256", "registry_sha256") if k in out}
    )
    write_json(REPORTS_DIR / "final_verdict.json", out)
    write_text(REPORTS_DIR / "FINAL_REPORT.md", _report(out))
    write_text(DOCS_DIR / "PHASE_53_COSTED_DECISION_EDGE.md", _docs(verdict, reason))
    print(
        {
            "phase": 53,
            "final_verdict": verdict,
            "verdict_reason": reason,
            "survivors": (out.get("discovery") or {}).get("survivors"),
            "confirmed": (out.get("confirmation") or {}).get("confirmed_ids"),
            "champion": champion,
            "production": production,
            "runtime": out["runtime"],
        }
    )
    return out


if __name__ == "__main__":
    main()
