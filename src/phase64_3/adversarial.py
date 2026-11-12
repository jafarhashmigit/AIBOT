"""Adversarial adoption checks."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_2.engine import HardenedLifecycleEngine
from phase64_3.approved_runtime import RuntimeAdoptionError, assert_hardened_runtime, make_approved_paper_engine
from phase64_3.constants import canonical_json_sha256
from phase64_3.entrypoint_audit import audit_entry_points


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    audit = audit_entry_points()
    cases.append(
        {
            "name": "approved_entry_exists",
            "pass": audit["n_approved"] >= 1 and audit["accidental_bypass_eliminated_for_approved_path"],
        }
    )
    cases.append(
        {
            "name": "legacy_explicitly_classified",
            "pass": audit["n_legacy_explicit"] >= 5 and audit["n_high_bypass_risk_legacy"] >= 3,
        }
    )

    with tempfile.TemporaryDirectory() as td:
        eng = make_approved_paper_engine(work=Path(td), policy=NullPolicy())
        g = assert_hardened_runtime(eng)
        cases.append(
            {
                "name": "runtime_assert_hardened",
                "pass": g["approved_paper_runtime"] and isinstance(eng, HardenedLifecycleEngine),
            }
        )

    # Reject superseded symbol profile
    rejected = False
    try:
        with tempfile.TemporaryDirectory() as td:
            make_approved_paper_engine(
                work=Path(td),
                policy=NullPolicy(),
                account_profile={"symbol": "XAUUSD", "digits": 2, "broker": "Exness"},
            )
    except RuntimeAdoptionError:
        rejected = True
    cases.append({"name": "reject_xauusd_profile", "pass": rejected})

    # Unapproved engine fails assert
    class Fake:
        hardening_version = "x"
        approved_paper_runtime = True

    failed = False
    try:
        assert_hardened_runtime(Fake())
    except RuntimeAdoptionError:
        failed = True
    cases.append({"name": "reject_unapproved_engine_class", "pass": failed})

    cases.append({"name": "order_send_prohibited", "pass": "order_send" in PROHIBITED_MT5_API})

    out = {
        "cases": cases,
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "pass": all(c.get("pass") for c in cases),
        "entrypoint_audit_sha256": audit.get("sha256"),
        "genuine_broker_deals": 0,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
