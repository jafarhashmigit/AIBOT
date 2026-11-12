"""Phase64.7 multi-dimension verdict."""

from __future__ import annotations

from typing import Any

from phase64_7.constants import UNAPPROVED


def dimension_scores(bundle: dict[str, Any]) -> dict[str, Any]:
    probe = bundle.get("probe") or {}
    recon = bundle.get("reconciliation") or {}
    security = bundle.get("api_security") or {}
    contract = bundle.get("contract") or {}
    integrity = bundle.get("integrity") or {}

    live = "CONNECTED" if probe.get("status") == "LIVE_PROBE_OK" else "BLOCKED_OR_UNAVAILABLE"
    return {
        "live_mt5_connectivity": live,
        "account_metadata_completeness": "COMPLETE" if recon.get("account_metadata_complete") else "INCOMPLETE",
        "xauusdm_metadata_completeness": "COMPLETE"
        if recon.get("xauusdm_critical_metadata_complete")
        else "INCOMPLETE",
        "api_security_review": "PASS" if security.get("pass") else "FAIL",
        "allowlist_status": "UNCHANGED",
        "contract_calculation_completeness": contract.get("contract_calculation_completeness", "INCOMPLETE"),
        "risk_policy_approval": UNAPPROVED,
        "execution_authorization": "NOT_AUTHORIZED",
        "integrity_ok": bool(integrity.get("checks_pass")),
    }


def choose_verdict(bundle: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    dims = dimension_scores(bundle)
    probe = bundle.get("probe") or {}
    recon = bundle.get("reconciliation") or {}
    adv = bundle.get("adversarial") or {}
    tests = bundle.get("unit_tests") or {}
    regs = bundle.get("regressions") or {}

    if probe.get("status") != "LIVE_PROBE_OK":
        return (
            "LIVE_MT5_PROBE_BLOCKED",
            f"Live probe blocked: {probe.get('block_reason') or probe.get('status')}",
            dims,
        )

    core = (
        recon.get("pass")
        and dims["account_metadata_completeness"] == "COMPLETE"
        and dims["xauusdm_metadata_completeness"] == "COMPLETE"
        and dims["api_security_review"] == "PASS"
        and dims["allowlist_status"] == "UNCHANGED"
        and dims["risk_policy_approval"] == UNAPPROVED
        and dims["execution_authorization"] == "NOT_AUTHORIZED"
        and adv.get("suite_pass")
        and tests.get("ok")
        and regs.get("ok")
        and dims["integrity_ok"]
    )
    if core and dims["contract_calculation_completeness"] == "COMPLETE":
        return (
            "LIVE_MT5_METADATA_VERIFIED",
            "Live RO probe verified critical account/XAUUSDm fields; allowlist unchanged; execution not authorized",
            dims,
        )
    if probe.get("status") == "LIVE_PROBE_OK":
        return (
            "LIVE_MT5_METADATA_PARTIAL",
            "Live probe succeeded but completeness, contract calc, or safety suite incomplete",
            dims,
        )
    return "LIVE_MT5_PROBE_BLOCKED", "Probe blocked", dims
