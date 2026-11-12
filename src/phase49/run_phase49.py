"""Phase 49 runner — ontology reset & non-overlapping discovery."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from phase49.acquisition import acquire_dates
from phase49.confirmation import run_confirmation
from phase49.connection import close_readonly, open_readonly
from phase49.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    DOCS_DIR,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MAX_WALL_SECONDS,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
)
from phase49.date_selection import freeze_date_selection
from phase49.discovery import baselines, evaluate_hypotheses
from phase49.events import build_events_for_dates
from phase49.independent import verify_events_sample, verify_selection
from phase49.inventory import inventory_fields
from phase49.progress import write_json, write_text
from phase49.qualification import choose_verdict
from phase49.registry import build_feature_registry, build_hypothesis_registry


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _docs(verdict: str, reason: str) -> str:
    return f"""# Phase 49 — Market Information Ontology Reset

**Recipe:** `{RECIPE_ID}`  
**Verdict:** `{verdict}`  
**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`

## Purpose
Test whether a new market-information ontology (not the Phase47 13 M5 features)
contains reproducible information about costed non-overlapping BUY/SELL net R.

## Constraints
- Phase44 validation dates locked
- Retired strategies not revived
- Confirmation dates opened only if discovery survivors exist
- No deep learning / RL / bandits

## Verdict
`{verdict}` — {reason}

See `reports/phase49/FINAL_REPORT.md`.
"""


def _report(p: dict[str, Any]) -> str:
    lines = [
        "# Phase 49 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{p['final_verdict']}`",
        f"**Champion:** `{p['champion']}` | **Production:** `{p['production']}`",
        "",
        f"## Executive",
        f"- {p['verdict_reason']}",
        "",
        "## 1. Independent date selection",
        f"- `{p.get('selection')}`",
        "",
        "## 2. Data coverage",
        f"- `{p.get('acquisition')}`",
        f"- Inventory: `{p.get('inventory')}`",
        "",
        "## 3. Feature ontology",
        f"- Features n=`{(p.get('feature_registry') or {}).get('n_features')}` sha=`{(p.get('feature_registry') or {}).get('registry_sha256')}`",
        f"- Hypotheses n=`{(p.get('hypothesis_registry') or {}).get('n_hypotheses')}`",
        "",
        "## 4–5. Leakage / events",
        f"- Events: `{ {k:v for k,v in (p.get('events_meta') or {}).items() if k!='by_day'} }`",
        "",
        "## 6–10. Discovery / stats / cost / confirmation",
        f"- Baselines: `{p.get('baselines')}`",
        f"- Discovery survivors: `{(p.get('discovery') or {}).get('survivors')}`",
        f"- Confirmation: `{p.get('confirmation')}`",
        "",
        "## 11–12. vs Phase47/48",
        "- Phase47/48: 13-feature overlapping M5 architecture had no skill.",
        "- Phase49: new ontology + non-overlapping events on new UNSEEN dates.",
        "",
        "## 13. Confirmed edge",
        f"- `{(p.get('confirmation') or {}).get('confirmed_ids')}`",
        "",
        "## 14. Limitations",
        "- Demo bid/ask ≠ live; commission/slippage UNKNOWN.",
        "- C04 prior-day range unavailable without extra prior-day download (excluded).",
        "- Date-block dependence remains; n_events ≠ independent n.",
        "",
        "## 15. Phase50",
        f"- `{p.get('phase50_recommendation')}`",
        "",
        "## Independent verification",
        f"- `{p.get('independent')}`",
        "",
        "## Safety",
        f"- Orders/Discord/Telegram/packages/holdout/commit/push/mt5 = "
        f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
        f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}/{MT5_CONNECTIONS}",
        f"- Runtime s: `{p['runtime'].get('DURATION_SECONDS')}`",
        "",
        "No Phase50 started. Champion remains NO_MODEL.",
        "",
    ]
    return "\n".join(lines)


def main() -> dict[str, Any]:
    t0 = time.perf_counter()
    start = _utc()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Freeze date selection BEFORE acquisition / outcomes
    selection = freeze_date_selection()
    sel_verify = verify_selection(selection)
    if not sel_verify["ok"]:
        payload = {
            "final_verdict": "RESEARCH_DESIGN_FAILURE",
            "verdict_reason": "Date selection hash/forbidden-date verification failed",
            "selection": selection,
            "independent": {"selection": sel_verify},
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "research_design_failure": "selection_verify_failed",
            "runtime": {"START_UTC": start, "END_UTC": _utc(), "DURATION_SECONDS": time.perf_counter() - t0},
        }
        write_json(REPORTS_DIR / "final_verdict.json", payload)
        write_text(REPORTS_DIR / "FINAL_REPORT.md", _report(payload))
        write_text(DOCS_DIR / "PHASE_49_MARKET_INFORMATION_ONTOLOGY_RESET.md", _docs(payload["final_verdict"], payload["verdict_reason"]))
        print(__import__("json").dumps({"final_verdict": payload["final_verdict"]}, indent=2))
        return payload

    # Freeze registries before evaluation (and before confirmation)
    feature_reg = build_feature_registry()
    hyp_reg = build_hypothesis_registry()

    # 2) Acquire
    conn = open_readonly()
    acquisition: dict[str, Any]
    if conn.get("status") != "connected_readonly":
        acquisition = {
            "ok": False,
            "error": conn.get("reason"),
            "completed_dates": [],
            "pending_dates": selection["selected_dates"],
            "ticks_total": 0,
            "stop_reason": "mt5_unavailable",
        }
    else:
        try:
            wall_deadline = time.monotonic() + MAX_WALL_SECONDS
            acquisition = acquire_dates(
                conn["handle"],
                selection["selected_dates"],
                server=conn.get("server"),
                terminal_build=conn.get("terminal_build"),
                wall_deadline=wall_deadline,
            )
            acquisition["ok"] = True
            acquisition["server"] = conn.get("server")
            acquisition["terminal_build"] = conn.get("terminal_build")
        finally:
            close_readonly(conn.get("handle"))

    write_json(REPORTS_DIR / "acquisition.json", {k: v for k, v in acquisition.items() if k != "results"})

    completed = list(acquisition.get("completed_dates") or [])
    discovery_dates = [d for d in selection["discovery_dates"] if d in completed]
    confirmation_dates = [d for d in selection["confirmation_dates"] if d in completed]

    payload: dict[str, Any] = {
        "phase": 49,
        "recipe_id": RECIPE_ID,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "selection": {
            "selected_n": selection["selected_n"],
            "selection_sha256": selection["selection_sha256"],
            "discovery_dates": selection["discovery_dates"],
            "confirmation_dates": selection["confirmation_dates"],
            "pool_n": selection["pool_n"],
            "algorithm": selection["algorithm"],
        },
        "acquisition": {
            "completed_n": len(completed),
            "completed_dates": completed,
            "pending_n": len(acquisition.get("pending_dates") or []),
            "ticks_total": acquisition.get("ticks_total"),
            "stop_reason": acquisition.get("stop_reason"),
            "server": acquisition.get("server"),
        },
        "feature_registry": {
            "n_features": feature_reg["n_features"],
            "registry_sha256": feature_reg["registry_sha256"],
            "vwap_included": False,
        },
        "hypothesis_registry": {
            "n_hypotheses": hyp_reg["n_hypotheses"],
            "hypothesis_registry_sha256": hyp_reg["hypothesis_registry_sha256"],
        },
    }

    if len(discovery_dates) < 8:
        verdict, reason = choose_verdict({**payload, "acquisition": {"completed_dates": completed}})
        payload["final_verdict"] = verdict
        payload["verdict_reason"] = reason
        payload["runtime"] = {"START_UTC": start, "END_UTC": _utc(), "DURATION_SECONDS": round(time.perf_counter() - t0, 6)}
        write_json(REPORTS_DIR / "final_verdict.json", payload)
        write_text(REPORTS_DIR / "FINAL_REPORT.md", _report(payload))
        write_text(DOCS_DIR / "PHASE_49_MARKET_INFORMATION_ONTOLOGY_RESET.md", _docs(verdict, reason))
        print(__import__("json").dumps({"final_verdict": verdict, "verdict_reason": reason, "completed_n": len(completed)}, indent=2))
        return payload

    inv = inventory_fields(discovery_dates[0])
    write_json(REPORTS_DIR / "field_inventory.json", inv)
    payload["inventory"] = inv

    # 3) Build discovery events (do NOT touch confirmation yet for feature selection)
    disc_pack = build_events_for_dates(discovery_dates)
    events_meta = {k: v for k, v in disc_pack.items() if k != "events"}
    write_json(REPORTS_DIR / "discovery_events_meta.json", events_meta)
    payload["events_meta"] = events_meta

    base = baselines(disc_pack["events"])
    write_json(REPORTS_DIR / "baselines.json", base)
    payload["baselines"] = base

    discovery = evaluate_hypotheses(disc_pack["events"], hyp_reg["hypotheses"], fit_edges=True)
    write_json(REPORTS_DIR / "discovery_results.json", discovery)
    payload["discovery"] = {
        "n_survivors": discovery["n_survivors"],
        "survivors": discovery["survivors"],
        "n_evaluated": discovery["n_evaluated"],
        "frozen_edges": discovery["frozen_edges"],
    }

    # Freeze discovery artifacts hash before confirmation
    freeze_blob = {
        "feature_registry_sha256": feature_reg["registry_sha256"],
        "hypothesis_registry_sha256": hyp_reg["hypothesis_registry_sha256"],
        "frozen_edges": discovery["frozen_edges"],
        "survivors": discovery["survivors"],
        "discovery_dates": discovery_dates,
        "confirmation_dates": confirmation_dates,
    }
    from phase49.constants import canonical_json_sha256

    freeze_blob["freeze_sha256"] = canonical_json_sha256(
        {k: v for k, v in freeze_blob.items() if k != "freeze_sha256"}
    )
    write_json(REPORTS_DIR / "discovery_freeze.json", freeze_blob)

    confirmation: dict[str, Any]
    if discovery["n_survivors"] == 0:
        confirmation = {
            "opened": False,
            "reason": "no_discovery_survivors — confirmation dates remain sealed",
            "n_confirmed": 0,
            "confirmed_ids": [],
            "sealed_dates": confirmation_dates,
        }
    else:
        # Open confirmation exactly once
        conf_pack = build_events_for_dates(confirmation_dates)
        write_json(
            REPORTS_DIR / "confirmation_events_meta.json",
            {k: v for k, v in conf_pack.items() if k != "events"},
        )
        survivor_hyps = [h for h in hyp_reg["hypotheses"] if h["hypothesis_id"] in discovery["survivors"]]
        confirmation = run_confirmation(
            confirmation_events=conf_pack["events"],
            survivor_hyps=survivor_hyps,
            frozen_edges=discovery["frozen_edges"],
        )
        write_json(REPORTS_DIR / "confirmation_results.json", confirmation)

    payload["confirmation"] = confirmation

    ind_events = verify_events_sample(disc_pack["events"], max_n=40)
    payload["independent"] = {"selection": sel_verify, "events": ind_events}
    write_json(REPORTS_DIR / "independent_verification.json", payload["independent"])
    if not ind_events["ok"]:
        payload["data_integrity_failure"] = "independent_event_outcome_mismatch_or_overlap"

    payload["phase50_recommendation"] = (
        None
        if discovery["n_survivors"] == 0
        else "If confirmed: calibrate decision head on confirmed family only; else stop expanding ontology variants."
    )

    verdict, reason = choose_verdict(payload)
    payload["final_verdict"] = verdict
    payload["verdict_reason"] = reason
    payload["runtime"] = {
        "START_UTC": start,
        "END_UTC": _utc(),
        "DURATION_SECONDS": round(time.perf_counter() - t0, 6),
    }
    # strip huge
    write_json(REPORTS_DIR / "final_verdict.json", payload)
    write_text(REPORTS_DIR / "FINAL_REPORT.md", _report(payload))
    write_text(DOCS_DIR / "PHASE_49_MARKET_INFORMATION_ONTOLOGY_RESET.md", _docs(verdict, reason))

    print(
        __import__("json").dumps(
            {
                "phase": 49,
                "recipe_id": RECIPE_ID,
                "final_verdict": verdict,
                "verdict_reason": reason,
                "selected_n": selection["selected_n"],
                "completed_n": len(completed),
                "discovery_events": disc_pack["n_events"],
                "survivors": discovery["survivors"],
                "confirmation": {
                    "opened": confirmation.get("opened"),
                    "confirmed": confirmation.get("confirmed_ids"),
                },
                "ticks_total": acquisition.get("ticks_total"),
                "champion": CHAMPION_STATUS,
                "production": PRODUCTION_FINAL_ACTION,
                "runtime": payload["runtime"],
            },
            indent=2,
        )
    )
    return payload


if __name__ == "__main__":
    main()
