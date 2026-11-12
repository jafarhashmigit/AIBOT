"""Phase 55 — end-to-end paper execution verification."""

from __future__ import annotations

import shutil
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase55.audit import audit_phase54
from phase55.constants import (
    CHAMPION_STATUS,
    DATA_ROOT,
    DOCS_DIR,
    ENGINEERING_POLICY_VERSION,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    STATE_DIR,
    TEST_HIST_DIR,
    TEST_SHADOW_DIR,
    canonical_json_sha256,
)
from phase55.data_select import select_verification_sample
from phase55.engineering_policy import EngineeringTestPolicy
from phase55.harness import VerificationHarness, assert_production_policy_untouched, load_day_bundle
from phase55.progress import write_json, write_text
from phase55.readiness import continuous_operation_audit
from phase55.risk_scenarios import run_risk_rejection_battery
from phase55.stores import production_counts, test_historical_store, test_shadow_store


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clear_test_namespace() -> None:
    for d in (TEST_HIST_DIR, TEST_SHADOW_DIR, STATE_DIR):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase55.tests.test_phase55")
    # Also Phase54 regression
    suite.addTests(loader.loadTestsFromName("phase54.tests.test_phase54"))
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def choose_verdict(p: dict[str, Any]) -> tuple[str, str]:
    if p.get("data_integrity_failure"):
        return "DATA_INTEGRITY_FAILURE", str(p["data_integrity_failure"])
    buy_ok = bool((p.get("buy_lifecycle") or {}).get("ok"))
    sell_ok = bool((p.get("sell_lifecycle") or {}).get("ok"))
    wait_ok = bool((p.get("wait_and_risk") or {}).get("ok"))
    recovery_ok = bool((p.get("recovery") or {}).get("ok"))
    isolation_ok = bool((p.get("isolation") or {}).get("ok"))
    indep_ok = bool((p.get("independent_ok")))
    tests_ok = bool((p.get("test_results") or {}).get("ok"))
    policy_ok = bool((p.get("production_policy") or {}).get("ok"))
    if all([buy_ok, sell_ok, wait_ok, recovery_ok, isolation_ok, indep_ok, tests_ok, policy_ok]):
        return (
            "PAPER_EXECUTION_VERIFIED",
            "BUY/SELL paper lifecycles verified on archived bid/ask; WAIT/risk/recovery/isolation/tests passed.",
        )
    if buy_ok or sell_ok:
        missing = [
            k
            for k, v in {
                "buy": buy_ok,
                "sell": sell_ok,
                "wait_risk": wait_ok,
                "recovery": recovery_ok,
                "isolation": isolation_ok,
                "independent": indep_ok,
                "tests": tests_ok,
                "policy": policy_ok,
            }.items()
            if not v
        ]
        return "PARTIALLY_VERIFIED", f"Incomplete verification: {missing}"
    return "ENGINEERING_BLOCKED", "BUY/SELL lifecycle verification failed"


def _docs(verdict: str, reason: str) -> str:
    return f"""# Phase 55 — End-to-End Paper Execution Verification

**Recipe:** `{RECIPE_ID}`  
**Verdict:** `{verdict}`  
**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`

{reason}

EngineeringTestPolicy (`{ENGINEERING_POLICY_VERSION}`) is test-only. Phase54 NullPolicy remains production default.

## Reproduce

```powershell
$env:PYTHONPATH='src'
.\\.venv\\Scripts\\python.exe -m unittest phase55.tests.test_phase55 phase54.tests.test_phase54 -v
.\\.venv\\Scripts\\python.exe -m phase55.run_phase55
```

See `reports/phase55/FINAL_REPORT.md`.
"""


def _report(p: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 55 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{p['final_verdict']}`",
            f"**Champion:** `{p['champion']}` | **Production:** `{p['production']}`",
            f"**Reason:** {p.get('verdict_reason')}",
            "",
            "## 1. Phase54 integration audit",
            f"- `{p.get('audit')}`",
            "",
            "## 2. BUY lifecycle evidence",
            f"- `{p.get('buy_lifecycle')}`",
            "",
            "## 3. SELL lifecycle evidence",
            f"- `{p.get('sell_lifecycle')}`",
            "",
            "## 4. WAIT and risk rejection",
            f"- `{p.get('wait_and_risk')}`",
            "",
            "## 5–6. Bid/ask + independent recomputation",
            f"- independent_ok=`{p.get('independent_ok')}`",
            f"- `{p.get('independent_details')}`",
            "",
            "## 7. Restart recovery",
            f"- `{p.get('recovery')}`",
            "",
            "## 8. Experience isolation",
            f"- `{p.get('isolation')}`",
            "",
            "## 9–10. Tests",
            f"- Phase54+55: `{p.get('test_results')}`",
            "",
            "## 11. Continuous-operation blockers",
            f"- `{p.get('readiness')}`",
            "",
            "## 12. Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m unittest phase55.tests.test_phase55 phase54.tests.test_phase54 -v",
            ".\\.venv\\Scripts\\python.exe -m phase55.run_phase55",
            "```",
            "",
            f"Runtime s: `{p.get('duration_s')}`",
            "",
            "No Phase56 started. Engineering-test trades ≠ strategy performance.",
        ]
    ) + "\n"


def main() -> dict[str, Any]:
    t0 = time.monotonic()
    start = _utc()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)

    prod_before = production_counts()
    audit = audit_phase54()
    sample = select_verification_sample(max_days=2)
    readiness = continuous_operation_audit()

    if not sample.get("selected"):
        payload = {
            "data_integrity_failure": "No archive day passed bid/ask path verification",
            "sample": sample,
            "audit": audit,
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
        }
        verdict, reason = choose_verdict(payload)
        payload.update({"final_verdict": verdict, "verdict_reason": reason, "duration_s": time.monotonic() - t0})
        write_json(REPORTS_DIR / "final_verdict.json", payload)
        write_text(REPORTS_DIR / "FINAL_REPORT.md", _report(payload))
        return payload

    _clear_test_namespace()
    day_meta = sample["selected"][0]
    day = day_meta["day"]
    bundle = load_day_bundle(day)
    m5, h1, by = bundle["m5"], bundle["h1"], bundle["ticks_by_bar"]
    idx = 48

    # --- BUY lifecycle ---
    h_buy = VerificationHarness(
        policy=EngineeringTestPolicy(["BUY"]),
        risk=RiskManager(),
        state_path=STATE_DIR / "buy_state.json",
    )
    buy_rec = h_buy.process_decision(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=idx)
    buy_ok = (
        not buy_rec.get("rejected")
        and (buy_rec.get("decision") or {}).get("action") == "BUY"
        and buy_rec.get("closed") is not None
        and buy_rec["closed"]["entry_fill"] == buy_rec["closed"]["entry_ask"]
        and buy_rec["closed"]["exit_fill"] == buy_rec["closed"]["exit_bid"]
        and (buy_rec.get("compare") or {}).get("ok") is True
    )
    # idempotent
    buy_skip = h_buy.process_decision(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=idx)

    # --- SELL lifecycle (next non-overlapping idx) ---
    sell_idx = idx + 12
    h_sell = VerificationHarness(
        policy=EngineeringTestPolicy(["SELL"]),
        risk=RiskManager(),
        state_path=STATE_DIR / "sell_state.json",
    )
    sell_rec = h_sell.process_decision(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=sell_idx)
    sell_ok = (
        not sell_rec.get("rejected")
        and (sell_rec.get("decision") or {}).get("action") == "SELL"
        and sell_rec.get("closed") is not None
        and sell_rec["closed"]["entry_fill"] == sell_rec["closed"]["entry_bid"]
        and sell_rec["closed"]["exit_fill"] == sell_rec["closed"]["exit_ask"]
        and (sell_rec.get("compare") or {}).get("ok") is True
    )

    # --- WAIT ---
    wait_idx = sell_idx + 12
    h_wait = VerificationHarness(
        policy=EngineeringTestPolicy(["WAIT"]),
        risk=RiskManager(),
        state_path=STATE_DIR / "wait_state.json",
    )
    wait_rec = h_wait.process_decision(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=wait_idx)
    wait_decision_ok = (wait_rec.get("decision") or {}).get("action") == "WAIT" and wait_rec.get("closed") is None

    # Risk battery on real observation
    obs_for_risk = buy_rec.get("observation") or {}
    risk_bat = run_risk_rejection_battery(obs_for_risk)
    risk_ok = all(
        risk_bat["summary"][k]["final_action"] == "WAIT"
        for k in (
            "spread_block",
            "invalid_stop",
            "daily_loss_block",
            "drawdown_block",
            "max_positions_block",
            "duplicate_block",
            "circuit_breaker",
        )
    ) and risk_bat["summary"]["wait_allowed"]["final_action"] == "WAIT"

    # Stale / invalid observation
    bad = h_wait.process_decision(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=5)
    stale_ok = bad.get("rejected") is True

    # --- Recovery: defer open, restart, complete ---
    rec_idx = wait_idx + 12
    if rec_idx + 1 + 12 >= len(m5) and len(sample["selected"]) > 1:
        day2 = sample["selected"][1]["day"]
        bundle2 = load_day_bundle(day2)
        m5r, h1r, byr = bundle2["m5"], bundle2["h1"], bundle2["ticks_by_bar"]
        day_r, idx_r = day2, 48
    else:
        m5r, h1r, byr = m5, h1, by
        day_r, idx_r = day, rec_idx if rec_idx + 13 < len(m5) else 60

    rec_state = STATE_DIR / "recovery_state.json"
    if rec_state.exists():
        rec_state.unlink()
    h_def = VerificationHarness(
        policy=EngineeringTestPolicy(["BUY"]),
        risk=RiskManager(),
        state_path=rec_state,
        defer_exit=True,
    )
    deferred = h_def.process_decision(day=day_r, m5=m5r, h1=h1r, ticks_by_bar=byr, idx=idx_r)
    open_n = len(h_def.risk.open_positions)
    # restart
    h_rec = VerificationHarness(
        policy=EngineeringTestPolicy(["WAIT"]),
        risk=RiskManager(),
        state_path=rec_state,
        defer_exit=False,
    )
    recovered = h_rec.continue_open_to_exit(day=day_r, m5=m5r, ticks_by_bar=byr)
    recovery_ok = (
        deferred.get("deferred") is True
        and open_n == 1
        and len(recovered) == 1
        and recovered[0]["closed"]["status"] == "CLOSED"
        and recovered[0]["compare"]["ok"] is True
        and len(h_rec.risk.open_positions) == 0
    )
    # duplicate prevention after recovery processed decision
    again = h_rec.process_decision(day=day_r, m5=m5r, h1=h1r, ticks_by_bar=byr, idx=idx_r)
    recovery_idempotent = again.get("skipped") is True

    # --- Isolation ---
    prod_after = production_counts()
    t_shadow = test_shadow_store()
    t_hist = test_historical_store()
    isolation = {
        "prod_before": prod_before,
        "prod_after": prod_after,
        "hist_unchanged": prod_before["hist_n"] == prod_after["hist_n"],
        "shadow_unchanged": prod_before["shadow_n"] == prod_after["shadow_n"],
        "test_shadow_n": t_shadow.n,
        "test_hist_n": t_hist.n,
        "test_paths": {"shadow": str(t_shadow.path), "hist": str(t_hist.path)},
        "all_test_tagged": all(r.get("ENGINEERING_TEST_ONLY") for r in t_shadow.all()),
    }
    isolation["ok"] = (
        isolation["hist_unchanged"]
        and isolation["shadow_unchanged"]
        and isolation["test_shadow_n"] > 0
        and "/phase55/" in isolation["test_paths"]["shadow"].replace("\\", "/").lower()
    )

    production_policy = assert_production_policy_untouched()
    # Extra: NullPolicy still constructs WAIT
    from phase54.decision import decide

    dnull = decide(obs_for_risk, obs_for_risk.get("features") or {}, None, {}, policy=NullPolicy())
    production_policy["null_still_wait"] = dnull["action"] == "WAIT"
    production_policy["ok"] = production_policy.get("ok") and production_policy["null_still_wait"]

    independent_ok = buy_ok and sell_ok and (recovered[0]["compare"]["ok"] if recovered else False)

    test_results = _run_tests()

    payload: dict[str, Any] = {
        "phase": 55,
        "recipe": RECIPE_ID,
        "audit": audit,
        "sample": {"day": day, "meta": day_meta, "selected_n": len(sample["selected"])},
        "buy_lifecycle": {
            "ok": buy_ok,
            "action": (buy_rec.get("decision") or {}).get("action"),
            "entry_fill": (buy_rec.get("closed") or {}).get("entry_fill"),
            "entry_ask": (buy_rec.get("closed") or {}).get("entry_ask"),
            "exit_fill": (buy_rec.get("closed") or {}).get("exit_fill"),
            "exit_bid": (buy_rec.get("closed") or {}).get("exit_bid"),
            "exit_reason": (buy_rec.get("closed") or {}).get("exit_reason"),
            "net_r": (buy_rec.get("closed") or {}).get("net_r"),
            "units": (buy_rec.get("closed") or {}).get("units"),
            "stop_loss": (buy_rec.get("closed") or {}).get("stop_loss"),
            "take_profit": (buy_rec.get("closed") or {}).get("take_profit"),
            "compare": buy_rec.get("compare"),
            "idempotent_skip": buy_skip.get("skipped"),
            "stages": buy_rec.get("stages"),
            "decision_id": (buy_rec.get("decision") or {}).get("decision_id"),
            "position_id": (buy_rec.get("closed") or {}).get("position_id"),
        },
        "sell_lifecycle": {
            "ok": sell_ok,
            "action": (sell_rec.get("decision") or {}).get("action"),
            "entry_fill": (sell_rec.get("closed") or {}).get("entry_fill"),
            "entry_bid": (sell_rec.get("closed") or {}).get("entry_bid"),
            "exit_fill": (sell_rec.get("closed") or {}).get("exit_fill"),
            "exit_ask": (sell_rec.get("closed") or {}).get("exit_ask"),
            "exit_reason": (sell_rec.get("closed") or {}).get("exit_reason"),
            "net_r": (sell_rec.get("closed") or {}).get("net_r"),
            "compare": sell_rec.get("compare"),
            "stages": sell_rec.get("stages"),
        },
        "wait_and_risk": {
            "ok": wait_decision_ok and risk_ok and stale_ok,
            "wait_action": (wait_rec.get("decision") or {}).get("action"),
            "wait_no_position": wait_rec.get("closed") is None,
            "risk_summary": risk_bat.get("summary"),
            "stale_rejected": stale_ok,
        },
        "independent_ok": independent_ok,
        "independent_details": {
            "buy": buy_rec.get("compare"),
            "sell": sell_rec.get("compare"),
            "recovery": recovered[0]["compare"] if recovered else None,
        },
        "recovery": {
            "ok": recovery_ok and recovery_idempotent,
            "deferred_open": open_n,
            "recovered_n": len(recovered),
            "compare": recovered[0]["compare"] if recovered else None,
            "idempotent_after": recovery_idempotent,
        },
        "isolation": isolation,
        "production_policy": production_policy,
        "readiness": readiness,
        "test_results": test_results,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "duration_s": time.monotonic() - t0,
        "runtime": {"START_UTC": start, "END_UTC": _utc()},
        "disclaimer": "Engineering-test trades are NOT strategy performance or profitability evidence.",
    }

    if prod_after["hist_n"] != prod_before["hist_n"] or prod_after["shadow_n"] != prod_before["shadow_n"]:
        payload["data_integrity_failure"] = "Production experience store counts changed during Phase55"

    verdict, reason = choose_verdict(payload)
    payload["final_verdict"] = verdict
    payload["verdict_reason"] = reason
    payload["artifact_sha256"] = canonical_json_sha256(
        {k: payload[k] for k in ("final_verdict", "verdict_reason", "sample") if k in payload}
    )

    write_json(REPORTS_DIR / "buy_lifecycle.json", payload["buy_lifecycle"])
    write_json(REPORTS_DIR / "sell_lifecycle.json", payload["sell_lifecycle"])
    write_json(REPORTS_DIR / "wait_risk.json", payload["wait_and_risk"])
    write_json(REPORTS_DIR / "recovery.json", payload["recovery"])
    write_json(REPORTS_DIR / "isolation.json", payload["isolation"])
    write_json(REPORTS_DIR / "final_verdict.json", payload)
    write_text(REPORTS_DIR / "FINAL_REPORT.md", _report(payload))
    write_text(DOCS_DIR / "PHASE_55_PAPER_EXECUTION_VERIFICATION.md", _docs(verdict, reason))

    print(
        {
            "phase": 55,
            "final_verdict": verdict,
            "verdict_reason": reason,
            "buy_ok": buy_ok,
            "sell_ok": sell_ok,
            "isolation_ok": isolation.get("ok"),
            "tests": test_results,
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
        }
    )
    return payload


if __name__ == "__main__":
    main()
