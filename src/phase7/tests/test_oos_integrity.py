import unittest

from phase7.constants import EXPECTED_ROWS, PHASE2_OOS_SHA256
from phase7.validation import audit_rows, file_sha256
from phase7.oos_adapter import load_oos


class OosIntegrityTests(unittest.TestCase):
    def test_phase2_oos_unchanged(self):
        self.assertEqual(file_sha256(), PHASE2_OOS_SHA256)
        rows = load_oos()
        report = audit_rows(rows)
        self.assertEqual(report["n"], EXPECTED_ROWS)
        self.assertTrue(report["unchanged"])
        self.assertEqual(report["after_cutoff"], 0)


if __name__ == "__main__":
    unittest.main()
