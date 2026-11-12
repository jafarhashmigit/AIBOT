"""Phase58 research integrity tests."""

from __future__ import annotations

import unittest

from phase54.decision import NullPolicy
from phase58.audit import build_research_audit
from phase58.constants import DO_NOT_REPEAT
from phase58.data import chronological_splits
from phase58.registry import HYPOTHESES, build_registry


class TestRegistry(unittest.TestCase):
    def test_no_forbidden_collisions(self):
        reg = build_registry()
        self.assertEqual(reg["forbidden_id_collisions"], [])
        for h in HYPOTHESES:
            self.assertNotIn(h["id"], DO_NOT_REPEAT)

    def test_audit_sha(self):
        a = build_research_audit()
        self.assertTrue(a.get("audit_sha256"))


class TestSplits(unittest.TestCase):
    def test_chrono_no_overlap(self):
        s = chronological_splits()
        d, v, h = set(s["discovery"]), set(s["validation"]), set(s["holdout_sealed"])
        self.assertEqual(len(d & v), 0)
        self.assertEqual(len(d & h), 0)
        self.assertEqual(len(v & h), 0)
        if s["discovery"] and s["validation"]:
            self.assertLess(s["discovery"][-1], s["validation"][0])


class TestNullPolicy(unittest.TestCase):
    def test_null_default(self):
        self.assertEqual(NullPolicy().version, "phase54_null_policy_v1")


if __name__ == "__main__":
    unittest.main()
