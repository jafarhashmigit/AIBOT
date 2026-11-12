"""Phase57.1 durable recovery tests — independent of Phase57 assumptions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.tests.fixtures import directional_path
from phase57_1.adversarial import run_inject_stage, run_rebuild_adversarial, run_subprocess_crash
from phase57_1.constants import EXPECTED_NULL_POLICY, deterministic_experience_id
from phase57_1.durable_engine import make_durable_engine
from phase57_1.journal import TradeLifecycleJournal
from phase57_1.rebuild import rebuild_experience_from_journal, wipe_store
from phase57_1.reconcile import reconcile
from phase57_1.suite import before_after_gap_comparison


class TestNullPolicy(unittest.TestCase):
    def test_default_null(self):
        with tempfile.TemporaryDirectory() as td:
            eng = make_durable_engine(work=Path(td))
            self.assertIsInstance(eng.policy, NullPolicy)
            self.assertEqual(eng.policy.version, EXPECTED_NULL_POLICY)


class TestJournalDurability(unittest.TestCase):
    def test_wipe_shadow_rebuilds_from_journal(self):
        with tempfile.TemporaryDirectory() as td:
            out = before_after_gap_comparison(Path(td))
            self.assertTrue(out["ok"], out)
            self.assertEqual(out["before"]["net_r"], out["after_recovery"]["net_r"])
            self.assertEqual(out["before"]["exit_reason"], out["after_recovery"]["exit_reason"])

    def test_repeated_rebuild_no_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            day, m5, h1, by = directional_path(move_after_entry=-5.0)
            eng = make_durable_engine(
                work=work,
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
            )
            eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            wipe_store(eng.shadow)
            rebuild_experience_from_journal(eng.journal, shadow=eng.shadow)
            n1 = eng.shadow.n
            rebuild_experience_from_journal(eng.journal, shadow=eng.shadow)
            self.assertEqual(n1, eng.shadow.n)
            self.assertEqual(n1, 1)

    def test_deterministic_experience_id(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            day, m5, h1, by = directional_path(move_after_entry=-5.0)
            eng = make_durable_engine(
                work=work,
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
            )
            eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            tid = eng.journal.committed_exits()[0]["txn_id"]
            eid = deterministic_experience_id(tid, "AGENT_SHADOW")
            self.assertEqual(eng.shadow.all()[0]["experience_id"], eid)

    def test_checksum_quarantine(self):
        with tempfile.TemporaryDirectory() as td:
            jdir = Path(td) / "journal"
            j = TradeLifecycleJournal(jdir)
            j.commit(
                stage="POSITION_OPEN",
                txn_id="t1",
                position_id="p1",
                payload={"side": "BUY"},
                experience_source="AGENT_SHADOW",
            )
            path = j.path
            with path.open("a", encoding="utf-8") as f:
                f.write(
                    '{"schema_version":"phase57_1_journal_v1","record_id":"x","txn_id":"y",'
                    '"position_id":"z","stage":"EXIT_COMMITTED","seq":2,"payload":{},'
                    '"provenance":"t","created_iso":"t","checksum":"nope"}\n'
                )
            j2 = TradeLifecycleJournal(jdir)
            self.assertTrue(len(list(j2.quarantine.glob("*"))) >= 1)
            self.assertFalse(any(r.get("txn_id") == "y" for r in j2.all()))


class TestAdversarial(unittest.TestCase):
    def test_rebuild_suite(self):
        with tempfile.TemporaryDirectory() as td:
            out = run_rebuild_adversarial(Path(td))
            self.assertTrue(out["ok"], out)

    def test_after_exit_commit_inject(self):
        with tempfile.TemporaryDirectory() as td:
            out = run_inject_stage("after_durable_exit_commit", Path(td))
            self.assertTrue(out["ok"], out)

    def test_after_outcome_before_experience(self):
        with tempfile.TemporaryDirectory() as td:
            out = run_inject_stage("after_outcome_before_experience", Path(td))
            self.assertTrue(out["ok"], out)

    def test_subprocess_after_exit_commit(self):
        with tempfile.TemporaryDirectory() as td:
            out = run_subprocess_crash(Path(td), "after_durable_exit_commit")
            self.assertTrue(out["ok"], out)
            self.assertGreaterEqual(out["n_exits"], 1)
            self.assertFalse(out["lost_committed_outcome"])


class TestReconcile(unittest.TestCase):
    def test_clean_reconcile(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            day, m5, h1, by = directional_path(move_after_entry=-5.0)
            eng = make_durable_engine(
                work=work,
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
            )
            eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            eng.persist()
            rep = reconcile(journal=eng.journal, state=eng.state, shadow=eng.shadow, hist=eng.hist)
            self.assertEqual(rep["missing_outcomes"], [])
            self.assertEqual(rep["duplicate_outcomes"], [])
            self.assertTrue(rep["ok"], rep)


if __name__ == "__main__":
    unittest.main()
