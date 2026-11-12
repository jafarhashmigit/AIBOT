"""Platform & collector capability discovery — no invented APIs."""

from __future__ import annotations

from typing import Any

from phase62.adapters import mt5_api_capability
from phase62.constants import PROJECT_ROOT, canonical_json_sha256


def discover_integrations() -> dict[str, Any]:
    mt5 = mt5_api_capability()
    # Search for CSV/history utilities (paths only)
    csv_hits = []
    for pat in ("**/*deal*.csv", "**/*history*.csv", "**/*orders*.csv"):
        csv_hits.extend([str(p.relative_to(PROJECT_ROOT)) for p in PROJECT_ROOT.glob(pat)][:10])
    mt_modules = []
    for rel in (
        "src/phase12/mt5_readonly.py",
        "src/phase12/mt5_allowlist.py",
        "src/phase16a/mt5_reader.py",
        "src/phase52/mt5_probe.py",
        "src/phase61/execution_evidence.py",
    ):
        p = PROJECT_ROOT / rel
        if p.is_file():
            mt_modules.append(rel)

    out = {
        "mt5_allowlist": mt5,
        "mt5_readonly_modules": mt_modules,
        "mt4_native_adapter_present": False,
        "csv_history_files_found_sample": csv_hits[:20],
        "credential_architecture": {
            "stores_passwords_in_repo": False,
            "env_example_broker_keys": False,
            "policy": "No credentials in source or reports",
        },
        "phase61_collector_interfaces": True,
        "live_connection_authorized": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def build_capability_matrix(identity: dict[str, Any], discovery: dict[str, Any]) -> dict[str, Any]:
    platform = identity.get("platform")
    mt5 = discovery.get("mt5_allowlist") or {}
    native_mt5_history = bool(mt5.get("history_deals_get_permitted"))
    rows = [
        {
            "capability": "platform_neutral_collector_interface",
            "status": "IMPLEMENTED",
            "safe": True,
            "notes": "Always available",
        },
        {
            "capability": "csv_import_adapter",
            "status": "IMPLEMENTED",
            "safe": True,
            "notes": "Requires broker-exported history with explicit column map",
        },
        {
            "capability": "json_fixture_adapter",
            "status": "IMPLEMENTED",
            "safe": True,
            "notes": "Synthetic fixtures for tests only — never enter genuine store",
        },
        {
            "capability": "native_mt5_history_deals_get",
            "status": "BLOCKED_BY_ALLOWLIST" if not native_mt5_history else "AVAILABLE_BUT_NOT_ACTIVATED",
            "safe": False if not native_mt5_history else "REQUIRES_SECURITY_REVIEW",
            "notes": (
                "Phase64.8 permitted history_deals_get as RO evidence; Phase62 does not activate native pull"
                if native_mt5_history
                else "Phase12 PROHIBITED_MT5_API includes history_deals_get; Phase62 does not expand allowlist or connect"
            ),
        },
        {
            "capability": "native_mt4_history_adapter",
            "status": "NOT_PRESENT",
            "safe": True,
            "notes": "Do not pretend MT5 adapter supports MT4",
        },
        {
            "capability": "live_order_submission",
            "status": "PROHIBITED",
            "safe": True,
            "notes": "order_send prohibited; live NOT_AUTHORIZED",
        },
        {
            "capability": "demo_read_only_terminal_session",
            "status": "NOT_ACTIVATED",
            "safe": True,
            "notes": "Platform UNKNOWN or unverified; no terminal connection in Phase62",
        },
    ]
    out = {
        "platform_from_identity": platform,
        "matrix": rows,
        "safest_viable_path": "CSV_OR_JSON_IMPORT_WITH_EXPLICIT_MAPPING",
        "native_adapter_prerequisites": [
            "Verified platform MT4 or MT5",
            "Verified demo environment",
            "Security-reviewed allowlist expansion if native history APIs required",
            "Non-secret account metadata intake completed",
            "Explicit read-only session policy",
        ],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def platform_integration_decision(identity: dict[str, Any], matrix: dict[str, Any]) -> dict[str, Any]:
    platform = str(identity.get("platform") or "UNKNOWN").upper()
    if platform in ("UNKNOWN", ""):
        decision = "PLATFORM_NEUTRAL_CSV_JSON_ONLY"
        reason = "Platform UNKNOWN — native adapter not activated; CSV/JSON import path selected"
    elif platform == "MT5":
        decision = "MT5_NATIVE_HISTORY_NOT_ACTIVATED_USE_CSV_JSON"
        reason = (
            "MT5 claimed; Phase62 still does not activate native history pull "
            "(Phase64.8 later permitted RO history APIs). Phase62 uses CSV/JSON without terminal connection"
        )
    elif platform == "MT4":
        decision = "MT4_NATIVE_NOT_PRESENT_USE_CSV_JSON"
        reason = "MT4 native adapter not present; CSV/JSON import path selected"
    else:
        decision = "UNSUPPORTED_PLATFORM_USE_CSV_JSON"
        reason = f"Platform {platform} unsupported for native adapter"

    out = {
        "decision": decision,
        "reason": reason,
        "activated_adapters": ["csv_import", "json_fixture_tests_only", "platform_neutral_store"],
        "native_terminal_connected": False,
        "orders_submitted": 0,
        "live_account_access": False,
        "matrix_sha256": matrix.get("sha256"),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
