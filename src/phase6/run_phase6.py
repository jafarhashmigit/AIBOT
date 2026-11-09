"""Phase 6 architecture validation. Unit tests only. No trading experiments."""

from __future__ import annotations

import sys
import unittest
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
    save,
    sha256_file,
    wrap,
)
from phase6.constants import PROTOCOL_ID, REPORTS_DIR, RESEARCH_CUTOFF, SEED


FROZEN_HASHES = {
    "src/data/xauusd_m5.csv": "ac34d06fdede8a71bfcc2170badb7c04acfad83e5ecb79a928f85276ef5a4760",
    "src/data/phase2_oos_predictions.csv": "6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f",
    "src/data/phase3_decision_journal.csv": "b8cc1da7cc5918d9fd17131c67913aad183f58098b2671d04c7cc1b024d5324a",
    "reports/phase4/regime_results.json": "c8565408b35f66c799c8183b6d39fa3ee0f9943c3e2144982e0dc2a8dc6efe55",
    "reports/phase5/replication_results.json": "39b74769bc63de7ec5c6b74d356aaca66f5d108cff24d8918998607741d05785",
    "src/features_m5.py": "b97a3ae579a72128d2a83ec6988f084b96a233b5bb698096b26c0a83d5212ccd",
    "src/label_m5.py": "72e5b6c525999fde30f9514dc7c1e0b8e825006bba173547adea9e2b64be81d2",
}


def run_tests() -> dict:
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


def hash_check() -> dict:
    out = {}
    for rel, expected in FROZEN_HASHES.items():
        path = ROOT / rel
        actual = sha256_file(path)
        out[rel] = {"expected": expected, "actual": actual, "unchanged": actual == expected}
    return out


def main() -> int:
    install_guards()
    GUARD["cutoff"] = RESEARCH_CUTOFF
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    tests = run_tests()
    hashes = hash_check()
    unchanged = all(v["unchanged"] for v in hashes.values())
    payload = {
        "protocol": PROTOCOL_ID,
        "tests": tests,
        "frozen_hashes_unchanged": unchanged,
        "hashes": hashes,
        "holdout": holdout_status(),
        "max_market_timestamp_accessed": None,
        "live_trading": False,
        "production_model": False,
        "ny_sell_retested": False,
        "finding": "PHASE 6 ARCHITECTURE COMPLETE — NO TRADING EDGE CLAIM",
    }
    save(
        REPORTS_DIR / "architecture_validation.json",
        wrap("phase6_architecture", "exploratory", {"recipe": PROTOCOL_ID}, payload, SEED),
    )
    assert_holdout_untouched()
    print("tests", tests)
    print("hashes_unchanged", unchanged)
    print("holdout", holdout_status())
    print("PHASE 6 ARCHITECTURE COMPLETE — NO TRADING EDGE CLAIM")
    return 0 if tests["ok"] and unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
