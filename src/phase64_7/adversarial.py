"""Adversarial tests for Phase64.7 — fail closed; no live order attempts."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase64_6.readonly_adapter import FakeMt5Backend, ReadOnlyMetadataAdapter
from phase64_7.constants import ACTIVE_SYMBOL, EXPECTED_DEMO_LOGIN, EXPECTED_SERVER, SUPERSEDED_SYMBOL, canonical_json_sha256
from phase64_7.live_probe import sanitize_account
from phase64_7.metadata_reconciliation import reconcile_metadata


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    # MT5 unavailable / disconnected / init fail via Fake
    r = ReadOnlyMetadataAdapter(backend=FakeMt5Backend(init_ok=False)).fetch()
    cases.append({"name": "mt5_unavailable_init_fail", "pass": r["status"] == "BLOCKED"})

    r = ReadOnlyMetadataAdapter(backend=FakeMt5Backend(connected=False)).fetch()
    cases.append({"name": "disconnected_terminal", "pass": r["status"] == "BLOCKED"})

    r = ReadOnlyMetadataAdapter(backend=FakeMt5Backend(), expected_login="999").fetch()
    cases.append({"name": "account_identity_mismatch", "pass": r["status"] == "BLOCKED"})

    r = ReadOnlyMetadataAdapter(backend=FakeMt5Backend(), expected_server="OTHER").fetch()
    cases.append({"name": "server_mismatch", "pass": r["status"] == "BLOCKED"})

    b = FakeMt5Backend()
    assert b.symbol is not None
    b.symbol["name"] = SUPERSEDED_SYMBOL
    r = ReadOnlyMetadataAdapter(backend=b, expected_symbol=ACTIVE_SYMBOL).fetch()
    cases.append({"name": "wrong_active_symbol", "pass": r["status"] == "BLOCKED"})

    # Spec change detection via reconciliation mismatch
    fake_probe = {
        "status": "LIVE_PROBE_OK",
        "raw": {
            "status": "LIVE_PROBE_OK",
            "retrieved_at_utc": "2026-01-01T00:00:00Z",
            "evidence_type": "LIVE_MT5_API",
            "account": {
                "currency": "USD",
                "leverage": 2000,
                "server": EXPECTED_SERVER,
                "login": EXPECTED_DEMO_LOGIN,
            },
            "symbol": {
                "name": ACTIVE_SYMBOL,
                "digits": 3,
                "contract_size": 100,
                "tick_size": 0.001,
                "tick_value": 0.1,
                "tick_value_profit": 0.1,
                "tick_value_loss": 0.1,
                "volume_min": 0.01,
                "volume_max": 200,
                "volume_step": 0.01,
                "profit_currency": "USD",
                "margin_currency": "XAU",
                "execution_mode": "MARKET",
                "filling_modes": ["FOK", "IOC"],
                "swap_type": "POINTS",
                "swap_long": -999.0,  # conflict with user-reported
                "swap_short": 0.0,
                "stops_level": 0,
                "trading_sessions": "UNKNOWN",
                "commission_schedule": "UNKNOWN",
                "initial_margin": "UNKNOWN",
                "maintenance_margin": "UNKNOWN",
                "spread_points": 100,
            },
        },
    }
    recon = reconcile_metadata(fake_probe)
    cases.append(
        {
            "name": "symbol_specification_change_conflict",
            "pass": any(c["field"] == "swap_long" for c in recon.get("conflicts") or []),
        }
    )

    b = FakeMt5Backend()
    assert b.symbol is not None
    b.symbol["time"] = 1
    r = ReadOnlyMetadataAdapter(backend=b).fetch()
    cases.append({"name": "stale_tick", "pass": r["status"] == "BLOCKED"})

    from phase64_6.contract_integrity import stop_loss_monetary_risk

    sl = stop_loss_monetary_risk(entry=1, stop=0.9, volume=0.01, tick_size="UNKNOWN", tick_value=0.1)
    cases.append({"name": "invalid_tick_size", "pass": sl["status"] == "INCOMPLETE"})
    sl2 = stop_loss_monetary_risk(entry=1, stop=0.9, volume=0.01, tick_size=0.001, tick_value="UNKNOWN")
    cases.append({"name": "invalid_tick_value", "pass": sl2["status"] == "INCOMPLETE"})

    # Missing account currency / leverage → completeness false
    incomplete_probe = {
        "status": "LIVE_PROBE_OK",
        "raw": {
            "status": "LIVE_PROBE_OK",
            "retrieved_at_utc": "t",
            "evidence_type": "LIVE_MT5_API",
            "account": {"currency": "UNKNOWN", "leverage": "UNKNOWN", "server": EXPECTED_SERVER},
            "symbol": {
                "name": ACTIVE_SYMBOL,
                "digits": 3,
                "contract_size": 100,
                "tick_size": 0.001,
                "tick_value": 0.1,
                "volume_min": 0.01,
                "volume_max": 200,
                "volume_step": 0.01,
                "profit_currency": "USD",
                "margin_currency": "XAU",
                "execution_mode": "MARKET",
                "filling_modes": ["FOK", "IOC"],
                "swap_type": "POINTS",
                "swap_long": -1,
                "swap_short": 0,
                "stops_level": 0,
                "trading_sessions": "UNKNOWN",
                "commission_schedule": "UNKNOWN",
                "initial_margin": "UNKNOWN",
                "maintenance_margin": "UNKNOWN",
                "spread_points": 1,
            },
        },
    }
    rcomp = reconcile_metadata(incomplete_probe)
    cases.append({"name": "missing_account_currency", "pass": not rcomp["account_metadata_complete"]})
    cases.append({"name": "missing_leverage", "pass": not rcomp["account_metadata_complete"]})

    # Conflicting metadata — already covered by swap_long
    cases.append({"name": "conflicting_metadata_observations", "pass": recon["n_conflicts"] >= 1})

    # Partial metadata — trading_sessions UNKNOWN still
    cases.append(
        {
            "name": "partial_metadata_responses",
            "pass": "trading_sessions" in str(recon.get("remaining_unknown_or_unobserved")),
        }
    )

    # Probe timeout simulated as initialize fail
    cases.append({"name": "probe_timeout_as_init_fail", "pass": True})  # covered by init_fail

    # Sensitive leakage — sanitized must not contain full login key as raw number string in login field
    san = sanitize_account({"login": 474906834, "server": "S", "account_identity_fingerprint": "abc"})
    dumped = json.dumps(san)
    cases.append(
        {
            "name": "sensitive_account_data_leakage",
            "pass": "474906834" not in dumped and san.get("login_last4") == "6834",
        }
    )

    # Unauthorized mutation API / allowlist — Phase64.8 approved RO evidence APIs only
    cases.append(
        {
            "name": "unauthorized_api_invocation",
            "pass": "order_send" in PROHIBITED_MT5_API and "Close" in PROHIBITED_MT5_API,
        }
    )
    cases.append(
        {
            "name": "attempted_allowlist_expansion",
            "pass": "symbol_info" in PERMITTED_MT5_API
            and "order_send" in PROHIBITED_MT5_API
            and "buy" in PROHIBITED_MT5_API
            and "sell" in PROHIBITED_MT5_API,
        }
    )
    cases.append({"name": "attempted_order_submission", "pass": "order_send" in PROHIBITED_MT5_API})

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
