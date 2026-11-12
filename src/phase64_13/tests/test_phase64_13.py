"""Unit tests for Phase 64.13 CLOSE_ONLY semantics."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_13.adversarial import run_adversarial_tests
from phase64_13.constants import (
    AUTOMATED_ORDERS,
    BREAK,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CLOSE_ONLY,
    CLOSED,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    OPEN,
    ORDER_SEND,
    PHASE65,
    RECIPE_ID,
    UNKNOWN,
)
from phase64_13.evidence_freeze import broker_evidence_freeze, risk_policy_status
from phase64_13.inspection import inspect_phase64_12_implementation
from phase64_13.integrity import audit_integrity
from phase64_13.lifecycle_safety import idempotent_exit_commit, monitor_under_session, run_lifecycle_session_matrix
from phase64_13.preflight import evaluate_session_gates
from phase64_13.schedule import build_corrected_schedule_spec, state_at_utc
from phase64_13.semantics import canonical_semantics


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_13_close_only_semantics_v1")

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        self.assertEqual(ORDER_SEND, "PROHIBITED")

    def test_invariants(self):
        self.assertIs(BROKER_SUBMISSION_ENABLED, False)
        self.assertIs(BROKER_EXECUTION_AUTHORIZED, False)
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")
        self.assertEqual(PHASE65, "NOT_STARTED")

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)


class TestDefectAndSemantics(unittest.TestCase):
    def test_defect_inspection(self):
        insp = inspect_phase64_12_implementation()
        self.assertTrue(insp["defect_confirmed"])
        self.assertEqual(insp["close_only_collapsed_into"], BREAK)

    def test_close_only_independent(self):
        sem = canonical_semantics()
        self.assertIn(CLOSE_ONLY, sem["states"])
        self.assertTrue(sem["close_only_ne_break"])
        self.assertNotEqual(CLOSE_ONLY, BREAK)
        self.assertNotEqual(CLOSE_ONLY, CLOSED)


class TestScheduleAndPreflight(unittest.TestCase):
    def test_close_only_state(self):
        r = state_at_utc(datetime(2026, 11, 10, 23, 1, 0, tzinfo=timezone.utc))
        self.assertEqual(r["state"], CLOSE_ONLY)

    def test_break_distinct(self):
        r = state_at_utc(datetime(2026, 11, 10, 22, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(r["state"], BREAK)

    def test_closed_weekend(self):
        r = state_at_utc(datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(r["state"], CLOSED)

    def test_open(self):
        r = state_at_utc(datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(r["state"], OPEN)

    def test_boundaries(self):
        self.assertTrue(build_corrected_schedule_spec()["boundary_probes_pass"])

    def test_close_only_rejects_entry(self):
        g = evaluate_session_gates(datetime(2026, 11, 10, 23, 1, 0, tzinfo=timezone.utc))
        self.assertTrue(g["reject_new_entry"])
        self.assertTrue(g["B_internal_position_monitoring"])
        self.assertFalse(g["D_execution_authorization"])

    def test_unknown_fail_closed(self):
        g = evaluate_session_gates(datetime(2026, 11, 10, 12, tzinfo=timezone.utc), force_state=UNKNOWN)
        self.assertTrue(g["reject_new_entry"])


class TestLifecycleAndFreeze(unittest.TestCase):
    def test_monitoring_all_states(self):
        for st in (OPEN, CLOSE_ONLY, BREAK, CLOSED, UNKNOWN):
            r = monitor_under_session(st)
            self.assertTrue(r["monitoring_enabled"])
            self.assertFalse(r["broker_order_submitted"])

    def test_idempotent_exit(self):
        self.assertTrue(idempotent_exit_commit()["no_duplicate_exit"])

    def test_lifecycle_matrix(self):
        m = run_lifecycle_session_matrix()
        self.assertTrue(m["all_states_monitoring_enabled"])
        self.assertTrue(m["synthetic_fixture_not_genuine"])

    def test_evidence_freeze(self):
        f = broker_evidence_freeze()
        self.assertEqual(f["rows"][0]["status"], "UNKNOWN")
        self.assertEqual(f["rows"][3]["status"], "VALIDATED")
        self.assertEqual(risk_policy_status()["overall"], "UNAPPROVED")


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])


if __name__ == "__main__":
    unittest.main()
