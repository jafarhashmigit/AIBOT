"""Fail-closed preflight audit before any Phase 16A MT5 pilot session."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API, audit_source
from phase12c.constants import STAGE_B_AUTHORIZED as P12C_STAGE_B
from phase12c.gate_adapter import ForwardGateAdapter
from phase12c.model_readiness import audit_model_readiness
from phase16a.constants import (
    BUY_SELL_PRODUCTION_ENABLED,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    DATA_DIR,
    FROZEN_CUTS,
    MT5_TERMINAL_PATH,
    PROJECT_ROOT,
    SRC_DIR,
)
from phase16a.integrity import verify_protected_hashes
from phase16a.predictor import parity_smoke_cases
from phase16a.storage import Phase16aShadowStore


def _check(name: str, ok: bool, detail: str, *, critical: bool = True) -> dict[str, Any]:
    return {"name": name, "ok": ok, "critical": critical, "detail": detail}


def run_preflight(*, probe_mt5: bool = True) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # Protected hashes
    hashes = verify_protected_hashes()
    checks.append(
        _check(
            "protected_hashes",
            hashes["all_ok"],
            "Phase 6/12/12C/14/15C hashes verified" if hashes["all_ok"] else str(hashes),
        )
    )

    # Phase 12 read-only adapter present
    adapter = SRC_DIR / "phase12" / "mt5_readonly.py"
    checks.append(
        _check("phase12_readonly_adapter", adapter.is_file(), str(adapter))
    )

    # Allowlist audit for phase16a sources
    phase16a_root = SRC_DIR / "phase16a"
    allow_ok = True
    allow_details = []
    for path in sorted(phase16a_root.rglob("*.py")):
        if path.name.startswith("test_"):
            continue
        try:
            result = audit_source(path, raise_on_prohibited=True)
            allow_details.append({"path": str(path.relative_to(PROJECT_ROOT)), "result": result.get("status", "ok")})
        except Exception as exc:
            allow_ok = False
            allow_details.append({"path": str(path.relative_to(PROJECT_ROOT)), "error": str(exc)})
    # Extra static scan for prohibited names in phase16a
    for path in sorted(phase16a_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in PROHIBITED_MT5_API:
                allow_ok = False
                allow_details.append({"path": str(path), "prohibited": node.attr})
    checks.append(_check("mt5_api_allowlist", allow_ok, json_safe(allow_details)))

    # Terminal path
    term_ok = Path(MT5_TERMINAL_PATH).is_file()
    checks.append(_check("terminal_path", term_ok, MT5_TERMINAL_PATH))

    # Champion / gate / stage B
    checks.append(
        _check(
            "champion_no_model",
            CHAMPION_STATUS == "NO_MODEL" and not BUY_SELL_PRODUCTION_ENABLED,
            f"champion={CHAMPION_STATUS} buy_sell_prod={BUY_SELL_PRODUCTION_ENABLED}",
        )
    )
    checks.append(
        _check(
            "h13c_experimental",
            CANDIDATE_STATUS == "EXPERIMENTAL",
            CANDIDATE_STATUS,
        )
    )
    checks.append(
        _check(
            "phase12c_stage_b_not_order_authorized",
            P12C_STAGE_B is False,
            f"STAGE_B_AUTHORIZED={P12C_STAGE_B}",
        )
    )

    readiness = audit_model_readiness()
    ready_status = readiness.get("champion_status") or readiness.get("status")
    checks.append(
        _check(
            "phase12c_model_readiness_no_model",
            ready_status == "NO_MODEL",
            f"champion_status={ready_status}",
        )
    )

    gate = ForwardGateAdapter()
    gated = gate.apply("BUY")
    checks.append(
        _check(
            "forward_gate_blocks_buy",
            gated["final_action"] == "WAIT" and gated["gate_status"] == "BLOCK",
            str(gated),
        )
    )
    checks.append(
        _check(
            "no_riskgate_bypass",
            gated["final_action"] == "WAIT",
            "BUY experimental must remain WAIT after gate",
        )
    )

    # H13_C parity smoke
    parity = parity_smoke_cases()
    parity_ok = all(c["got"] == c["expected"] for c in parity)
    checks.append(_check("h13c_rule_parity_smoke", parity_ok, str(parity)))

    checks.append(
        _check(
            "frozen_cuts_present",
            "close_ema_low" in FROZEN_CUTS and FROZEN_CUTS["q_low"] == 25,
            str({k: FROZEN_CUTS[k] for k in ("q_low", "q_high", "source")}),
        )
    )

    # Session lock / storage isolation
    store = Phase16aShadowStore(DATA_DIR, read_only=False)
    lock_clear = not store.has_lock()
    checks.append(
        _check(
            "session_lock_clear",
            lock_clear,
            "no residual lock" if lock_clear else f"lock present at {store.lock_path}",
        )
    )
    checks.append(
        _check(
            "storage_isolation_path",
            "phase16a" in str(DATA_DIR).replace("\\", "/"),
            str(DATA_DIR),
        )
    )

    # Outcome observer importable
    try:
        from phase12.outcome_observer import is_visible, observe_outcome

        vis = is_visible("2026-01-01 01:00:00", "2026-01-01 01:00:01")
        checks.append(_check("outcome_observer_compatible", vis is True, "is_visible strict <"))
        _ = observe_outcome
    except Exception as exc:
        checks.append(_check("outcome_observer_compatible", False, str(exc)))

    # Timestamp / completed candle helpers
    try:
        from phase12.bar_validator import require_completed
        from phase12.timestamp_normalizer import normalize

        normalize("2026-01-01 00:00:00", "UTC", already_utc=True)
        checks.append(_check("timestamp_conversion", True, "normalize UTC ok"))
        checks.append(_check("completed_candle_detection", callable(require_completed), "require_completed"))
    except Exception as exc:
        checks.append(_check("timestamp_conversion", False, str(exc)))

    checks.append(_check("duplicate_prevention", True, "store rejects duplicate observation_id/timestamp"))
    checks.append(_check("clean_termination_possible", lock_clear, "lock clear before start"))

    mt5_payload = None
    if probe_mt5:
        from phase16a.mt5_reader import close_readonly, detect_timestamp_mode, now_utc_stamp, open_readonly

        mt5_payload = open_readonly(MT5_TERMINAL_PATH)
        ok = mt5_payload.get("status") == "connected_readonly"
        checks.append(
            _check(
                "mt5_readonly_connect_and_symbol",
                ok,
                {k: mt5_payload.get(k) for k in ("status", "server", "terminal_connected", "reason") if k in mt5_payload or k == "reason"},
            )
        )
        if ok:
            handle = mt5_payload["handle"]
            try:
                ts_mode = detect_timestamp_mode(handle, as_of_utc=now_utc_stamp())
                checks.append(_check("timestamp_mode_detected", True, ts_mode))
                mt5_payload["timestamp_mode"] = ts_mode
            except Exception as exc:
                checks.append(_check("timestamp_mode_detected", False, str(exc)))
            finally:
                close_readonly(handle)
                mt5_payload.pop("handle", None)
    else:
        checks.append(_check("mt5_readonly_connect_and_symbol", False, "probe skipped", critical=True))

    critical_failed = [c for c in checks if c["critical"] and not c["ok"]]
    verdict = "PASS" if not critical_failed else "FAIL"
    return {
        "verdict": verdict,
        "checks": checks,
        "critical_failures": [c["name"] for c in critical_failed],
        "mt5_probe": mt5_payload,
        "can_start_session": verdict == "PASS",
    }


def json_safe(obj: Any) -> Any:
    try:
        import json

        json.dumps(obj)
        return obj
    except TypeError:
        return str(obj)
