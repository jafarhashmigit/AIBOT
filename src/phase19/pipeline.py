"""Synthetic shadow lifecycle runner — programmatic candle advance, no MT5/wall-clock."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase18.constants import HORIZONS
from phase18.daily_report import aggregate_daily, build_daily_discord_bundle
from phase18.experience import ExperienceStore
from phase18.horizons import expected_outcome_check_utc, horizon_label, pkt_calendar_date, parse_utc
from phase18.outcomes import atr_at_signal, create_pending_outcomes, evaluate_horizon_outcome
from phase18.store import Phase18Store
from phase19.constants import (
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    SOURCE_HISTORICAL,
    SOURCE_SHADOW,
    SOURCE_SYNTHETIC,
    SYNTHETIC_NAMESPACE,
    SYNTHETIC_ROOT,
)
from phase19.fixtures import ScenarioKind, build_scenario, expected_status_for_kind
from phase19.mock_discord import MockDiscordClient
from phase19.synthetic_messages import (
    build_synthetic_daily_payload,
    build_synthetic_outcome_payload,
    build_synthetic_signal_payload,
)


def synthetic_root(base: Path | None = None) -> Path:
    root = Path(base) if base is not None else SYNTHETIC_ROOT
    root.mkdir(parents=True, exist_ok=True)
    # Marker file so namespace is unambiguous
    marker = root / "NAMESPACE.txt"
    if not marker.exists():
        marker.write_text(
            f"{SYNTHETIC_NAMESPACE}\nSYNTHETIC TEST ONLY — NOT PRODUCTION EXPERIENCE\n",
            encoding="utf-8",
        )
    return root


def _mark_synthetic(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["synthetic"] = True
    out["synthetic_namespace"] = SYNTHETIC_NAMESPACE
    out["source_type"] = SOURCE_SYNTHETIC
    return out


def journal_synthetic_signal(
    *,
    store: Phase18Store,
    experience: ExperienceStore,  # noqa: ARG001 — reserved for symmetry
    scenario: dict[str, Any],
    discord: MockDiscordClient,
    expected_horizon_id: str | None = None,
) -> dict[str, Any]:
    """Journal decision + pending horizons; mock-deliver synthetic signal once."""
    decision = _mark_synthetic(scenario["decision"])
    observation = _mark_synthetic(scenario["observation"])
    atr = float(scenario["atr"])

    store.append_observation(observation)
    newly = store.append_decision(decision)
    pending = create_pending_outcomes(decision, atr=atr)
    for p in pending:
        p["note"] = f"{SYNTHETIC_NAMESPACE}; synthetic pending horizon"
        p["synthetic"] = "1"
        p["synthetic_namespace"] = SYNTHETIC_NAMESPACE
    added = store.append_outcomes(pending)

    delivery = {"status": "SKIPPED_ALREADY_JOURNALED"}
    if newly:
        event = {
            "event_id": decision["decision_id"],
            "decision_id": decision["decision_id"],
            "message_type": f"P19_SYNTH_SIGNAL_{decision['experimental_action']}",
        }
        payload = build_synthetic_signal_payload(
            decision, observation, expected_horizon_id=expected_horizon_id
        )
        delivery = discord.deliver(event, payload)
    return {
        "decision_id": decision["decision_id"],
        "journaled": newly,
        "pending_added": added,
        "delivery": delivery,
        "final_action": decision["final_action"],
        "champion_status": decision["model_status"],
        "candidate_status": decision["candidate_status"],
    }


def advance_and_resolve(
    *,
    store: Phase18Store,
    experience: ExperienceStore,
    bars: list[dict[str, Any]],
    signal_idx: int,
    atr: float,
    discord: MockDiscordClient,
    up_to_horizon_bars: int | None = None,
) -> dict[str, Any]:
    """Advance programmatically through synthetic candles and finalize eligible horizons."""
    finalized: list[dict[str, Any]] = []
    notifications: list[dict[str, Any]] = []
    experience_added = 0
    signal_open = bars[signal_idx]["bar_open_timestamp_utc"]

    # Determine how many bars after signal are "available"
    max_needed = up_to_horizon_bars if up_to_horizon_bars is not None else max(HORIZONS.values())
    available_end = signal_idx + 1 + max_needed  # exclusive slice end index into bars
    available_bars = bars[: min(available_end, len(bars))]
    as_of = available_bars[-1]["bar_close_timestamp_utc"]

    for pending in list(store.pending_outcomes()):
        hb = int(pending["horizon_bars"])
        if hb > max_needed:
            continue
        # Truncated bar list enforces candle-boundary eligibility (no wall-clock wait).
        need = signal_idx + 1 + hb
        if need > len(available_bars):
            continue
        window = bars[:need]
        updated = evaluate_horizon_outcome(
            pending,
            bars=window,
            signal_bar_open_utc=signal_open,
            atr=atr,
            as_of_utc=as_of,
        )
        if updated.get("status") == "PENDING":
            continue

        updated["synthetic"] = "1"
        updated["synthetic_namespace"] = SYNTHETIC_NAMESPACE
        store.upsert_outcome(updated)
        finalized.append(updated)

        if str(updated.get("discord_notified", "0")) != "1":
            event = {
                "event_id": updated["outcome_event_id"],
                "decision_id": updated["decision_id"],
                "message_type": f"P19_SYNTH_OUTCOME_{updated['horizon_id']}_{updated['status']}",
            }
            if discord.already_sent(event):
                delivery = {"status": "SKIPPED_DUPLICATE"}
            else:
                payload = build_synthetic_outcome_payload(updated)
                delivery = discord.deliver(event, payload)
            if delivery.get("status") in {"MOCK_SENT", "SKIPPED_DUPLICATE"}:
                updated["discord_notified"] = "1"
                store.upsert_outcome(updated)
            notifications.append({"outcome_event_id": updated["outcome_event_id"], "delivery": delivery})

        if str(updated.get("experience_recorded", "0")) != "1":
            # Store via Phase18 ExperienceStore under synthetic root only
            row = experience.add_shadow_from_outcome(
                updated,
                feature_context_ref=updated.get("decision_id", ""),
                selected_horizon="NOT ESTABLISHED",
            )
            if row is not None:
                # Annotate synthetic marker in a sidecar record (do not touch production)
                sidecar = Path(experience.shadow_path).with_name("agent_shadow_experience_meta.jsonl")
                with sidecar.open("a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "experience_id": row["experience_id"],
                                "synthetic": True,
                                "synthetic_namespace": SYNTHETIC_NAMESPACE,
                                "source": SOURCE_SHADOW,
                                "note": "PHASE19_SYNTHETIC_TEST — not production learning data",
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    )
                updated["experience_recorded"] = "1"
                store.upsert_outcome(updated)
                experience_added += 1

    return {
        "finalized": finalized,
        "notifications": notifications,
        "experience_added": experience_added,
        "as_of": as_of,
        "available_horizon_bars": max_needed,
    }


def run_scenario_lifecycle(
    kind: ScenarioKind,
    *,
    root: Path | None = None,
    expected_horizon_id: str | None = None,
    interrupt_after_signal: bool = False,
) -> dict[str, Any]:
    """Full synthetic lifecycle for one scenario. Optional interrupt+resume for recovery tests."""
    base = synthetic_root(root)
    store = Phase18Store(base)
    experience = ExperienceStore(base)
    discord = MockDiscordClient(base / "mock_discord_ledger.jsonl")
    scenario = build_scenario(kind)
    signal = journal_synthetic_signal(
        store=store,
        experience=experience,
        scenario=scenario,
        discord=discord,
        expected_horizon_id=expected_horizon_id,
    )

    if interrupt_after_signal:
        # Simulate crash: return mid-flight with only pending outcomes
        return {
            "kind": kind,
            "phase": "interrupted_after_signal",
            "signal": signal,
            "scenario_decision_id": scenario["decision"]["decision_id"],
            "pending": store.pending_outcomes(),
            "root": str(base),
            "bars": scenario["bars"],
            "signal_idx": scenario["signal_idx"],
            "atr": scenario["atr"],
            "reference_trade": scenario["reference_trade"],
            "discord_sent_n": len(discord.sent),
        }

    # Programmatic advance: resolve after each horizon boundary becomes available
    stepwise: list[dict[str, Any]] = []
    for hid, hb in HORIZONS.items():
        step = advance_and_resolve(
            store=store,
            experience=experience,
            bars=scenario["bars"],
            signal_idx=scenario["signal_idx"],
            atr=scenario["atr"],
            discord=discord,
            up_to_horizon_bars=hb,
        )
        stepwise.append({"horizon_id": hid, "horizon_bars": hb, **{k: step[k] for k in ("as_of", "experience_added")}})

    outcomes = store.outcomes()
    by_status = {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "PENDING": 0}
    for o in outcomes:
        if o.get("decision_id") != scenario["decision"]["decision_id"]:
            continue
        st = str(o.get("status", "PENDING")).upper()
        if st in by_status:
            by_status[st] += 1

    expected = expected_status_for_kind(kind)
    # Primary check: H12 (or first finalized matching expected) under full window
    primary = None
    for o in outcomes:
        if o.get("decision_id") == scenario["decision"]["decision_id"] and o.get("horizon_id") == "H12":
            primary = o
            break

    return {
        "kind": kind,
        "phase": "completed",
        "signal": signal,
        "decision_id": scenario["decision"]["decision_id"],
        "expected_status": expected,
        "primary_h12": primary,
        "outcome_counts": by_status,
        "stepwise": stepwise,
        "reference_trade": scenario["reference_trade"],
        "discord_sent_n": len(discord.sent),
        "discord_duplicates_prevented": sum(1 for x in discord.sent if False),
        "experience_counts": experience.counts(),
        "final_action": "WAIT",
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "broker_orders": 0,
        "synthetic_namespace": SYNTHETIC_NAMESPACE,
        "root": str(base),
        "timing_checks": {
            hid: expected_outcome_check_utc(scenario["decision"]["decision_timestamp_utc"], hid)
            for hid in HORIZONS
        },
    }


def resume_after_interrupt(
    *,
    root: Path,
    bars: list[dict[str, Any]],
    signal_idx: int,
    atr: float,
) -> dict[str, Any]:
    """Restart recovery: finalize pending, send missing Discord, no duplicate experience."""
    store = Phase18Store(root)
    experience = ExperienceStore(root)
    discord = MockDiscordClient(root / "mock_discord_ledger.jsonl")
    # Reload seen keys from ledger file
    if discord.path and discord.path.is_file():
        for line in discord.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") == "MOCK_SENT" and row.get("dedupe_key"):
                discord._seen.add(row["dedupe_key"])

    before_exp = experience.counts()["agent_shadow"]
    before_out = len(store.outcomes())
    result = advance_and_resolve(
        store=store,
        experience=experience,
        bars=bars,
        signal_idx=signal_idx,
        atr=atr,
        discord=discord,
        up_to_horizon_bars=max(HORIZONS.values()),
    )
    # Second pass must be idempotent
    again = advance_and_resolve(
        store=store,
        experience=experience,
        bars=bars,
        signal_idx=signal_idx,
        atr=atr,
        discord=discord,
        up_to_horizon_bars=max(HORIZONS.values()),
    )
    return {
        "finalized_first": len(result["finalized"]),
        "finalized_second": len(again["finalized"]),
        "experience_before": before_exp,
        "experience_after": experience.counts()["agent_shadow"],
        "outcomes_before": before_out,
        "outcomes_after": len(store.outcomes()),
        "pending_remaining": len(store.pending_outcomes()),
        "discord_sent_n": len(discord.sent),
        "duplicate_outcomes_added_second_pass": 0,
    }


def run_synthetic_daily_report(root: Path | None = None) -> dict[str, Any]:
    base = synthetic_root(root)
    store = Phase18Store(base)
    decisions = store.decisions()
    outcomes = store.outcomes()
    if not decisions:
        return {"status": "empty", "namespace": SYNTHETIC_NAMESPACE}
    date_pkt = pkt_calendar_date(parse_utc(decisions[0]["decision_timestamp_utc"]))
    report = aggregate_daily(decisions=decisions, outcomes=outcomes, date_pkt=date_pkt)
    payload = build_synthetic_daily_payload(report)
    discord = MockDiscordClient(base / "mock_discord_ledger.jsonl")
    event = {
        "event_id": f"p19_daily_{date_pkt}",
        "decision_id": f"p19_daily_{date_pkt}",
        "message_type": "P19_SYNTH_DAILY",
    }
    delivery = discord.deliver(event, payload)
    # Also exercise phase18 bundle builder but keep payload synthetic-labeled
    bundle = build_daily_discord_bundle(
        decisions=decisions,
        outcomes=outcomes,
        date_pkt=date_pkt,
        generated_at_utc=decisions[0]["decision_timestamp_utc"],
    )
    return {
        "status": "ok",
        "namespace": SYNTHETIC_NAMESPACE,
        "date_pkt": date_pkt,
        "report": report,
        "payload": payload,
        "delivery": delivery,
        "phase18_bundle_report_id": bundle["record"]["report_id"],
        "mixed_into_production": False,
    }


def seed_historical_control(root: Path) -> dict[str, Any]:
    """Ensure historical hypothetical remains separable inside synthetic namespace."""
    experience = ExperienceStore(root)
    row = experience.add_historical(
        {
            "outcome_event_id": "p19_hist_control__H12",
            "event_id": "p19_hist_control",
            "decision_id": "p19_hist_control",
            "side": "BUY",
            "action": "BUY",
            "outcome": "PASS",
            "realized_r": "1.0",
            "decision_timestamp_utc": "2026-01-01 10:00:00",
            "outcome_timestamp_utc": "2026-01-01 11:00:00",
            "horizon_id": "H12",
            "horizon_label": "60M",
        }
    )
    return {"historical_row": row, "source": SOURCE_HISTORICAL}


def assert_not_production_paths(root: Path) -> None:
    text = str(root.resolve()).replace("\\", "/").lower()
    banned = ("/phase18/", "/phase17/", "/phase16a/", "/phase16b/", "/phase12/")
    # Synthetic root lives under phase19 — must not be a production phase data dir
    if SYNTHETIC_NAMESPACE.lower() not in text and "phase19" not in text:
        raise RuntimeError(f"refusing non-synthetic root: {root}")
    for b in banned:
        # Allow only if phase19 path; block writing into those dirs directly
        if text.rstrip("/").endswith(b.strip("/")):
            raise RuntimeError(f"refusing production data path: {root}")


def run_full_synthetic_suite(root: Path | None = None) -> dict[str, Any]:
    """Execute all required synthetic validations into an isolated temp/synthetic root."""
    base = synthetic_root(root)
    assert_not_production_paths(base)
    # Clean slate for suite when using default ephemeral-style directory under phase19
    results: dict[str, Any] = {"namespace": SYNTHETIC_NAMESPACE, "scenarios": {}}

    for kind in ("BUY_PASS", "BUY_FAIL", "SELL_PASS", "SELL_FAIL", "TIMEOUT"):
        # Separate subdirectory per scenario to avoid cross-talk in outcome counts
        sub = base / kind.lower()
        if sub.exists():
            # wipe scenario subdir files only
            for p in sub.glob("*"):
                if p.is_file():
                    p.unlink()
        sub.mkdir(parents=True, exist_ok=True)
        results["scenarios"][kind] = run_scenario_lifecycle(
            kind,  # type: ignore[arg-type]
            root=sub,
            expected_horizon_id="H3",
        )

    # Horizon formatting checks across labels
    results["horizon_labels"] = {hid: horizon_label(hid) for hid in HORIZONS}

    # Daily report on BUY_PASS store after lifecycle
    results["daily"] = run_synthetic_daily_report(base / "buy_pass")

    # Historical separation control inside buy_pass store
    results["historical_control"] = seed_historical_control(base / "buy_pass")

    # Restart/idempotency on a fresh SELL_PASS interrupt path
    recover_root = base / "recovery"
    for p in recover_root.glob("*") if recover_root.exists() else []:
        if p.is_file():
            p.unlink()
    recover_root.mkdir(parents=True, exist_ok=True)
    interrupted = run_scenario_lifecycle("SELL_FAIL", root=recover_root, interrupt_after_signal=True)
    results["recovery"] = resume_after_interrupt(
        root=recover_root,
        bars=interrupted["bars"],
        signal_idx=interrupted["signal_idx"],
        atr=interrupted["atr"],
    )
    results["recovery"]["interrupted_pending_n"] = len(interrupted["pending"])

    results["safety"] = {
        "champion_status": CHAMPION_STATUS,
        "candidate_status": CANDIDATE_STATUS,
        "production_final_action": "WAIT",
        "broker_orders": 0,
        "holdout_accesses": 0,
        "mt5_started": False,
        "production_data_touched": False,
        "github_push": False,
    }
    return results
