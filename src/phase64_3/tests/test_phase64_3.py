"""Phase 64.3 tests — approved hardened runtime adoption."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_2.engine import HardenedLifecycleEngine
from phase64_3.adversarial import run_adversarial_tests
from phase64_3.approved_runtime import RuntimeAdoptionError, assert_hardened_runtime, make_approved_paper_engine
from phase64_3.constants import EXPECTED_NULL_POLICY, RECIPE_ID
from phase64_3.entrypoint_audit import audit_entry_points
from phase64_3.integrity import audit_integrity, phase58_holdout
from phase64_3.multibar_suite import run_multibar_suite
from phase64_3.recovery_suite import run_recovery_suite
from phase64_3.verdict import choose_verdict
from phase64_3.xauusdm_profile import audit_xauusdm_integrity


class TestSafety(unittest.TestCase):
    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_3_hardened_paper_runtime_adoption_v1")

    def test_holdout(self):
        self.assertEqual(len(phase58_holdout()), 10)

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)


class TestAdoption(unittest.TestCase):
    def test_approved_factory(self):
        with tempfile.TemporaryDirectory() as td:
            eng = make_approved_paper_engine(work=Path(td), policy=NullPolicy())
            self.assertIsInstance(eng, HardenedLifecycleEngine)
            g = assert_hardened_runtime(eng)
            self.assertTrue(g["approved_paper_runtime"])

    def test_reject_xauusd(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeAdoptionError):
                make_approved_paper_engine(
                    work=Path(td),
                    policy=NullPolicy(),
                    account_profile={"symbol": "XAUUSD", "digits": 2},
                )

    def test_entrypoint_audit(self):
        a = audit_entry_points()
        self.assertGreaterEqual(a["n_approved"], 1)
        self.assertGreaterEqual(a["n_legacy_explicit"], 5)

    def test_xauusdm(self):
        x = audit_xauusdm_integrity()
        self.assertTrue(x["pass"], x)


class TestSuites(unittest.TestCase):
    def test_multibar(self):
        s = run_multibar_suite()
        self.assertTrue(s["suite_pass"], s)

    def test_recovery(self):
        s = run_recovery_suite()
        self.assertTrue(s["suite_pass"], s)

    def test_adversarial(self):
        a = run_adversarial_tests()
        self.assertTrue(a["pass"], a)


class TestIntegrity(unittest.TestCase):
    def test_integrity(self):
        a = audit_integrity()
        self.assertFalse(a["phase0_64_2_source_modified"])
        self.assertTrue(a["checks_pass"])

    def test_verdict(self):
        v, _ = choose_verdict(
            adoption_ok=True,
            multibar_ok=True,
            recovery_ok=True,
            xau_ok=True,
            integrity_ok=True,
            tests_ok=True,
            null_ok=True,
        )
        self.assertEqual(v, "HARDENED_RUNTIME_ADOPTION_VALIDATED")


if __name__ == "__main__":
    unittest.main()
