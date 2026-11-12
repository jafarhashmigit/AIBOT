"""Phase64.6 multi-dimension verdict — do not conflate dimensions."""

from __future__ import annotations

from typing import Any

from phase64_6.constants import UNAPPROVED


def dimension_scores(bundle: dict[str, Any]) -> dict[str, Any]:
    arch = bundle.get("architecture") or {}
    matrix = bundle.get("security_matrix") or {}
    adapter = bundle.get("adapter") or {}
    contract = bundle.get("contract") or {}
    risk = bundle.get("risk_policy") or {}
    gate = bundle.get("execution_gate") or {}
    adv = bundle.get("adversarial") or {}
    integ = bundle.get("integrity") or {}
    tests = bundle.get("unit_tests") or {}
    genuine = bundle.get("genuine_evidence") or {}

    engineering_ok = all(
        [
            arch.get("pass"),
            matrix.get("pass"),
            adapter.get("engineering_pass"),
            contract.get("pass"),
            gate.get("pass"),
            adv.get("suite_pass"),
            integ.get("checks_pass"),
            tests.get("ok"),
        ]
    )
    meta_complete = bool((contract.get("metadata_completeness") or {}).get("complete"))
    risk_status = (risk.get("with_demo_balance_still_unapproved") or risk).get("approval_status", UNAPPROVED)
    if isinstance(risk.get("with_demo_balance_still_unapproved"), dict):
        risk_status = risk["with_demo_balance_still_unapproved"].get("approval_status", UNAPPROVED)
    exec_status = "NOT_AUTHORIZED"
    if gate.get("submission_reachable"):
        exec_status = "REACHABLE_INVARIANT_BROKEN"
    genuine_deals = int(genuine.get("genuine_broker_deals") or 0)

    return {
        "engineering_readiness": "PASS" if engineering_ok else "FAIL",
        "broker_metadata_completeness": "COMPLETE" if meta_complete else "INCOMPLETE",
        "risk_policy_approval_status": risk_status,
        "execution_authorization_status": exec_status,
        "genuine_broker_evidence_count": genuine_deals,
    }


def choose_verdict(bundle: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    dims = dimension_scores(bundle)
    eng = dims["engineering_readiness"]
    meta = dims["broker_metadata_completeness"]
    blocked_caps = (bundle.get("security_matrix") or {}).get("minimum_ro_capabilities_blocked_pending_review") or []

    # VALIDATED: engineering foundation closed for *available* RO APIs + fail-closed gates,
    # even if metadata incomplete and positions/history still blocked (honest).
    if eng == "PASS" and dims["execution_authorization_status"] == "NOT_AUTHORIZED":
        if meta == "INCOMPLETE" or blocked_caps:
            # Still validated for the RO engineering scope if tests prove fail-closed
            return (
                "MT5_READ_ONLY_READINESS_VALIDATED",
                "RO adapter/gates/contract calculators validated; metadata incomplete; positions/history APIs still blocked pending separate review",
                dims,
            )
        return (
            "MT5_READ_ONLY_READINESS_VALIDATED",
            "Read-only readiness engineering validated under current allowlist",
            dims,
        )
    if eng == "PASS" or meta == "INCOMPLETE":
        return (
            "MT5_READ_ONLY_READINESS_PARTIAL",
            "Partial engineering or incomplete metadata/security posture",
            dims,
        )
    return (
        "MT5_READ_ONLY_READINESS_BLOCKED",
        "Critical readiness engineering or safety checks failed",
        dims,
    )
