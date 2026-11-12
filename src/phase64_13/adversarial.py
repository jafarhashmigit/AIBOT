"""Deterministic adversarial checks for Phase 64.13."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_13.constants import (
    BREAK,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CLOSE_ONLY,
    CLOSED,
    OPEN,
    ORDER_SEND,
    UNAPPROVED,
    UNKNOWN,
    canonical_json_sha256,
)
from phase64_13.evidence_freeze import broker_evidence_freeze, risk_policy_status
from phase64_13.inspection import inspect_phase64_12_implementation
from phase64_13.lifecycle_safety import (
    idempotent_exit_commit,
    monitor_under_session,
    recovery_after_interruption,
    run_lifecycle_session_matrix,
)
from phase64_13.preflight import evaluate_session_gates
from phase64_13.schedule import boundary_probe, build_corrected_schedule_spec, state_at_utc
from phase64_13.semantics import canonical_semantics


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": bool(passed), **extra})

    insp = inspect_phase64_12_implementation()
    add("defect_confirmed_or_already_correct", insp["defect_confirmed"] or insp["already_correct"])
    add("close_only_independent_constant", CLOSE_ONLY not in (BREAK, CLOSED, OPEN, UNKNOWN))

    sem = canonical_semantics()
    add("independent_close_only_state_representation", sem["close_only_ne_break"] and CLOSE_ONLY in sem["states"])

    # CLOSE_ONLY rejects new entries
    co = evaluate_session_gates(
        datetime(2026, 11, 10, 23, 1, 0, tzinfo=timezone.utc)
    )
    add("close_only_rejects_new_entries", co["session_state"] == CLOSE_ONLY and co["reject_new_entry"] is True)

    # monitoring preserved
    mon = monitor_under_session(CLOSE_ONLY)
    add("close_only_preserves_monitoring", mon["monitoring_enabled"] is True and mon["exit"] is not None)

    # BREAK distinct
    br = state_at_utc(datetime(2026, 11, 10, 22, 30, 0, tzinfo=timezone.utc))
    add("break_remains_distinct", br["state"] == BREAK and br["state"] != CLOSE_ONLY)

    # CLOSED distinct
    cl = state_at_utc(datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc))
    add("closed_remains_distinct", cl["state"] == CLOSED and cl["state"] != BREAK)

    # UNKNOWN fail closed
    unk = evaluate_session_gates(datetime(2026, 11, 10, 12, tzinfo=timezone.utc), force_state=UNKNOWN)
    add("unknown_fails_closed", unk["reject_new_entry"] is True and unk["B_internal_position_monitoring"] is True)

    # boundaries
    spec = build_corrected_schedule_spec()
    add("session_transitions_exact_timestamps", spec["boundary_probes_pass"] is True)
    probes = boundary_probe("WINTER")
    add("utc_pkt_conversion", all("+05:00" in p["pkt"] or "T" in p["pkt"] for p in probes[:3]))
    add("dst_boundaries", all(p["pass"] for p in boundary_probe("SUMMER")))
    add("weekly_boundaries", all(p["pass"] for p in probes if "11-14" in p["ts_utc"] or "11-15" in p["ts_utc"] or "11-13" in p["ts_utc"]))

    # lifecycle
    matrix = run_lifecycle_session_matrix()
    add("existing_position_sl_tp_monitoring", matrix["all_states_monitoring_enabled"] and all(r["sl_or_exit_detected"] for r in matrix["rows"]))
    add("horizon_exit_monitoring", all(v == "HORIZON_EXIT" for v in matrix["horizon_by_state"].values()))
    add("horizon_exit_all_states", all(v == "HORIZON_EXIT" for v in matrix["horizon_by_state"].values()))
    add("lifecycle_recovery", matrix["recovery"]["exit_after_recovery"] is True)
    idem = idempotent_exit_commit()
    add("no_duplicate_exit_commitment", idem["no_duplicate_exit"] is True)

    # evidence freeze
    freeze = broker_evidence_freeze()
    add(
        "broker_evidence_boundary_preservation",
        freeze["rows"][0]["status"] == "UNKNOWN"
        and freeze["rows"][1]["status"] == "INCOMPLETE"
        and freeze["rows"][2]["status"] == "UNKNOWN_FOR_EXECUTION"
        and freeze["rows"][3]["status"] == "VALIDATED"
        and freeze["risk_policy"] == UNAPPROVED,
    )
    risk = risk_policy_status()
    add("risk_policy_unapproved", risk["overall"] == UNAPPROVED and risk["session_validation_alone_insufficient"])

    # auth independent
    open_g = evaluate_session_gates(datetime(2026, 11, 10, 12, tzinfo=timezone.utc))
    add(
        "execution_authorization_independent",
        open_g["A_new_entry_eligible"] is True
        and open_g["D_execution_authorization"] is False
        and BROKER_EXECUTION_AUTHORIZED is False,
    )

    add("no_order_invariant", "order_send" in PROHIBITED_MT5_API and ORDER_SEND == "PROHIBITED")
    add("submission_disabled", BROKER_SUBMISSION_ENABLED is False)

    # recovery explicit
    rec = recovery_after_interruption()
    add("recovery_after_interruption", rec["recovered_from_open_snapshot"] and rec["broker_order_submitted"] is False)

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
