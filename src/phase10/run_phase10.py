"""Phase 10: dual-source experience architecture validation. Research only."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
ROOT = SRC.parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phase3.nplib import (
    GUARD,
    assert_holdout_untouched,
    holdout_status,
    install_guards,
    read_csv_dicts,
    save,
    wrap,
)
from phase7.oos_adapter import load_paired
from phase10.constants import (
    MAX_ACCESS_TIMESTAMP,
    PHASE9_REPLAY_PATH,
    RECIPE_ID,
    REPORTS_DIR,
    RESEARCH_CUTOFF,
    SEED,
    SOURCE_HISTORICAL,
    SOURCE_PAPER,
)
from phase10.experience_intelligence import ExperienceIntelligence, load_paper_decisions_from_phase9
from phase10.historical_store import load_completed_historical
from phase10.paper_simulator import (
    PaperSimulator,
    assert_no_broker_surface,
    broker_order_calls,
    live_market_connections,
)
from phase10.paper_store import PaperExperienceStore
from phase10.tests.factories import entry, paper_decision
from phase10.validation import snapshot_protected


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def _hash_obj(obj) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def run_tests() -> dict:
    import unittest
    loader = unittest.TestLoader()
    suite = loader.discover(str(Path(__file__).parent / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        "ok": result.wasSuccessful(),
    }


def _build_state():
    pairs, eval_rows, oos_integrity = load_paired()
    hist, skipped, max_hist_ts = load_completed_historical(
        pairs, eval_rows, as_of=MAX_ACCESS_TIMESTAMP
    )
    paper = PaperExperienceStore()
    phase9_rows = read_csv_dicts(PHASE9_REPLAY_PATH)
    max_paper_ts = load_paper_decisions_from_phase9(phase9_rows, paper)
    intel = ExperienceIntelligence(hist, paper)
    summary = intel.summary(MAX_ACCESS_TIMESTAMP)
    max_ts = max(max_hist_ts, max_paper_ts)
    return {
        "oos_integrity": oos_integrity,
        "historical_store_n": len(hist),
        "historical_skipped": skipped,
        "paper_decisions": paper.decision_count(),
        "paper_trades": paper.trade_count(),
        "summary": summary,
        "max_ts": max_ts,
        "intel": intel,
        "paper": paper,
        "hist": hist,
    }


def _simulator_fixture() -> dict:
    paper = PaperExperienceStore()
    allowed = paper_decision("2026-06-19 10:00:00", raw="BUY", final="BUY", gate="ALLOW")
    blocked = paper_decision("2026-06-19 10:05:00", raw="SELL", final="WAIT", gate="BLOCK")
    waiting = paper_decision("2026-06-19 10:10:00", raw="WAIT", final="WAIT", gate="ALLOW")
    paper.record_decision(allowed)
    paper.record_decision(blocked)
    paper.record_decision(waiting)
    sim = PaperSimulator(paper)
    wait_rejected = False
    block_rejected = False
    try:
        sim.open_trade(waiting, entry("2026-06-19 10:10:00"))
    except Exception:
        wait_rejected = True
    try:
        sim.open_trade(blocked, entry("2026-06-19 10:05:00"))
    except Exception:
        block_rejected = True
    trade = sim.open_trade(allowed, entry("2026-06-19 10:00:00"))
    equal_rejected = False
    try:
        sim.complete_trade(
            trade,
            as_of="2026-06-19 11:00:00",
            exit_timestamp="2026-06-19 11:00:00",
            exit_price=2320.0,
            exit_reason="TP",
            realized_r=1.5,
            net_pnl=3.0,
            provenance="synthetic_fixture",
        )
    except Exception:
        equal_rejected = True
    outcome = sim.complete_trade(
        trade,
        as_of="2026-06-19 11:05:00",
        exit_timestamp="2026-06-19 11:00:00",
        exit_price=2320.0,
        exit_reason="TP",
        realized_r=1.5,
        net_pnl=3.0,
        provenance="synthetic_fixture",
    )
    return {
        "wait_rejected": wait_rejected,
        "block_rejected": block_rejected,
        "equal_timestamp_rejected": equal_rejected,
        "completed_after_horizon": outcome.outcome_status == "completed",
        "trade_id": trade.paper_trade_id,
        "completed_visible": len(paper.query_completed("2026-06-19 11:05:00")) == 1,
        "broker_order_calls": broker_order_calls(),
        "live_market_connections": live_market_connections(),
    }


def classify(tests_ok, source_ok, temporal_ok, intel_ok, sim_ok, repro_ok, integrity_ok) -> str:
    if not source_ok or not temporal_ok:
        return "DUAL-SOURCE EXPERIENCE ARCHITECTURE REJECTED"
    if not tests_ok or not intel_ok or not sim_ok or not repro_ok or not integrity_ok:
        return "DUAL-SOURCE EXPERIENCE ARCHITECTURE VALIDATION INCOMPLETE"
    return "DUAL-SOURCE EXPERIENCE ARCHITECTURE VALIDATED"


def main() -> int:
    install_guards()
    GUARD["cutoff"] = RESEARCH_CUTOFF
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    integrity_before = snapshot_protected()
    tests = run_tests()
    assert_no_broker_surface()

    print("state 1", flush=True)
    a = _build_state()
    print("state 2", flush=True)
    b = _build_state()
    sim_a = _simulator_fixture()
    sim_b = _simulator_fixture()

    det_ok = (
        _hash_obj(a["summary"]) == _hash_obj(b["summary"])
        and a["historical_store_n"] == b["historical_store_n"]
        and a["paper_decisions"] == b["paper_decisions"]
        and sim_a == sim_b
    )
    source_ok = (
        a["summary"]["historical"]["source_type"] == SOURCE_HISTORICAL
        and a["summary"]["paper"]["source_type"] == SOURCE_PAPER
        and a["summary"]["merged_raw_records"] is False
        and a["summary"]["makes_trading_decisions"] is False
        and a["summary"]["risk_gate_modified"] is False
    )
    temporal_ok = True
    hist_latest = a["summary"]["historical"]["latest_outcome_end"]
    if hist_latest is not None and not (hist_latest < MAX_ACCESS_TIMESTAMP):
        temporal_ok = False
    if a["max_ts"] > MAX_ACCESS_TIMESTAMP:
        temporal_ok = False
    intel_ok = (
        a["summary"]["historical"]["record_count"] == a["historical_store_n"]
        and a["summary"]["paper"]["trade_count"] == 0
        and a["summary"]["paper"]["completed_count"] == 0
        and a["summary"]["paper"]["decision_count"] == a["paper_decisions"]
    )
    sim_ok = all(sim_a[k] is True for k in (
        "wait_rejected", "block_rejected", "equal_timestamp_rejected",
        "completed_after_horizon", "completed_visible",
    )) and sim_a["broker_order_calls"] == 0 and sim_a["live_market_connections"] == 0
    integrity_after = snapshot_protected()
    integrity_ok = all(v["unchanged"] for v in integrity_after.values())
    holdout = holdout_status()

    conclusion = classify(
        bool(tests["ok"]), source_ok, temporal_ok, intel_ok, sim_ok, det_ok, integrity_ok
    )

    architecture = {
        "conclusion": conclusion,
        "historical_record_count": a["historical_store_n"],
        "historical_skipped_incomplete": a["historical_skipped"],
        "paper_decision_count": a["paper_decisions"],
        "paper_trade_count": a["paper_trades"],
        "paper_completed_count": a["summary"]["paper"]["completed_count"],
        "max_timestamp": a["max_ts"],
        "as_of": MAX_ACCESS_TIMESTAMP,
        "live_trading": False,
        "risk_gate_modified": False,
        "pushed": False,
    }
    source_separation = {
        "historical_source": SOURCE_HISTORICAL,
        "paper_source": SOURCE_PAPER,
        "merged_raw_records": False,
        "passed": source_ok,
    }
    temporal = {
        "boundary": "outcome_end < as_of",
        "as_of": MAX_ACCESS_TIMESTAMP,
        "latest_historical_outcome_end": hist_latest,
        "max_timestamp_accessed": a["max_ts"],
        "passed": temporal_ok,
    }
    intel_report = {
        "summary": a["summary"],
        "passed": intel_ok,
        "read_only": True,
    }
    sim_report = {**sim_a, "passed": sim_ok}
    repro = {
        "passed": det_ok,
        "hash_summary_1": _hash_obj(a["summary"]),
        "hash_summary_2": _hash_obj(b["summary"]),
        "hash_simulator_1": _hash_obj(sim_a),
        "hash_simulator_2": _hash_obj(sim_b),
        "seed": SEED,
        "note": "no RNG used; seed recorded for convention only",
    }

    cfg = {"recipe": RECIPE_ID, "as_of": MAX_ACCESS_TIMESTAMP}
    save(REPORTS_DIR / "architecture_validation.json", wrap("phase10_architecture", "exploratory", cfg, architecture, SEED))
    save(REPORTS_DIR / "source_separation.json", wrap("phase10_source_sep", "exploratory", cfg, source_separation, SEED))
    save(REPORTS_DIR / "temporal_validation.json", wrap("phase10_temporal", "exploratory", cfg, temporal, SEED))
    save(REPORTS_DIR / "paper_simulator_validation.json", wrap("phase10_simulator", "exploratory", cfg, sim_report, SEED))
    save(REPORTS_DIR / "experience_intelligence_validation.json", wrap("phase10_intel", "exploratory", cfg, intel_report, SEED))
    save(REPORTS_DIR / "reproducibility.json", wrap("phase10_repro", "exploratory", cfg, repro, SEED))

    payload = wrap("phase10_conclusion", "exploratory", cfg, {
        "conclusion": conclusion,
        "tests": tests,
        "architecture": architecture,
        "source_separation": source_separation,
        "temporal": temporal,
        "intelligence": intel_report,
        "simulator": sim_report,
        "reproducibility": repro,
        "integrity_before_ok": all(v["unchanged"] for v in integrity_before.values()),
        "integrity_after_ok": integrity_ok,
        "holdout": holdout,
        "broker_order_calls": broker_order_calls(),
        "live_market_connections": live_market_connections(),
        "packages_changed": 0,
        "pushed": False,
    }, SEED)
    save(REPORTS_DIR / "phase10_conclusion.json", payload)

    assert_holdout_untouched()
    print("tests", tests, flush=True)
    print("historical", a["historical_store_n"], "skipped", a["historical_skipped"], flush=True)
    print("paper decisions", a["paper_decisions"], "trades", a["paper_trades"], flush=True)
    print("max_ts", a["max_ts"], "holdout", holdout, flush=True)
    print("source", source_ok, "temporal", temporal_ok, "intel", intel_ok, "sim", sim_ok, "repro", det_ok, flush=True)
    print(conclusion, flush=True)
    return 0 if conclusion == "DUAL-SOURCE EXPERIENCE ARCHITECTURE VALIDATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
