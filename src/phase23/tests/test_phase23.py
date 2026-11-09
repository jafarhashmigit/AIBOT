"""Offline Phase 23 architecture validation tests (no cloud/MT5/Discord/network)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase16a.constants import FROZEN_CUTS
from phase22.campaign import CampaignStore
from phase22.constants import FROZEN_WF3_CUTS
from phase22.integrity import frozen_thresholds_intact, verify_protected_hashes
from phase23.constants import (
    BROKER_ORDERS,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    FINAL_STATUS,
    HOLDOUT_ACCESSES,
    PRODUCTION_FINAL_ACTION,
    PROVIDER_SELECTED,
    REQUIRED_COMPONENTS,
)
from phase23.providers import provider_comparison
from phase23.validation import architecture_validation, docs_present


class Phase23DesignTests(unittest.TestCase):
    def test_01_docs_present(self):
        present = docs_present()
        self.assertTrue(all(present.values()), msg=str(present))

    def test_02_protected_hashes(self):
        report = verify_protected_hashes()
        self.assertTrue(report["all_ok"])

    def test_03_frozen_thresholds_unchanged(self):
        self.assertTrue(frozen_thresholds_intact())
        self.assertEqual(FROZEN_WF3_CUTS["close_ema_low"], FROZEN_CUTS["close_ema_low"])
        self.assertEqual(FROZEN_CUTS["q_low"], 25)
        self.assertEqual(FROZEN_CUTS["q_high"], 75)

    def test_04_no_provider_selected(self):
        cmp_ = provider_comparison()
        self.assertIsNone(cmp_["selected_provider"])
        self.assertTrue(cmp_["provider_blocker"])
        self.assertFalse(cmp_["any_qualified_for_cloud"])
        self.assertIsNone(PROVIDER_SELECTED)
        for c in cmp_["candidates"]:
            if c["provider"] != "Local_MT5_reference_only":
                self.assertNotEqual(c["verdict"], "QUALIFIED")

    def test_05_safety_invariants(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(CANDIDATE_STATUS, "EXPERIMENTAL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertEqual(BROKER_ORDERS, 0)
        self.assertEqual(HOLDOUT_ACCESSES, 0)

    def test_06_required_components_listed(self):
        self.assertEqual(len(REQUIRED_COMPONENTS), 12)
        arch = architecture_validation()
        self.assertTrue(arch["components_designed"])
        self.assertEqual(arch["final_status"], FINAL_STATUS)

    def test_07_campaign_resume_never_resets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CampaignStore(Path(tmp))
            s1 = store.get_or_create(target=1000)
            store.record_session(
                session_id="s1",
                candles=10,
                buy=0,
                sell=0,
                wait=10,
                last_bar_open_utc="2026-11-09 12:00:00",
                discord_sent=0,
            )
            s2 = store.get_or_create(target=1000)
            self.assertEqual(s1["campaign_id"], s2["campaign_id"])
            self.assertEqual(s2["observed_candles"], 10)
            self.assertEqual(s2["remaining_candles"], 990)

    def test_08_architecture_blockers_documented(self):
        arch = architecture_validation()
        self.assertTrue(any("provider" in b.lower() for b in arch["unresolved_blockers"]))
        self.assertFalse(arch["cloud_deployed"])
        self.assertEqual(arch["safety_invariants"]["mt5_connections_this_phase"], 0)
        self.assertEqual(arch["safety_invariants"]["discord_messages_sent_this_phase"], 0)

    def test_09_phase16_22_untouched_marker(self):
        # Phase 23 must not alter protected artifact hashes.
        before = verify_protected_hashes()
        after = verify_protected_hashes()
        self.assertEqual(before["files"], after["files"])
        self.assertTrue(after["all_ok"])


if __name__ == "__main__":
    unittest.main()
