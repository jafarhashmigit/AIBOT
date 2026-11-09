import unittest

from phase8.experience_store import ExperienceStore
from phase8.tests.factories import record


class StoreRetrievalTests(unittest.TestCase):
    def test_a_incomplete_not_in_store(self):
        store = ExperienceStore()
        # Only completed records can be appended; incomplete never becomes queryable.
        self.assertEqual(store.query("2026-06-19 10:30:00"), [])

    def test_b_boundary_equal_not_visible(self):
        store = ExperienceStore()
        store.append(record("2026-06-19 10:00:00", "2026-06-19 11:00:00"))
        visible = store.query("2026-06-19 11:00:00")
        self.assertEqual(len(visible), 0)

    def test_c_future_excluded(self):
        store = ExperienceStore()
        store.append(record("2026-06-19 10:00:00", "2026-06-19 11:00:00"))
        self.assertEqual(store.query("2026-06-19 10:05:00"), [])
        self.assertEqual(store.query("2026-06-19 10:59:00"), [])
        self.assertEqual(len(store.query("2026-06-19 11:00:01")), 1)

    def test_d_size_never_decreases(self):
        store = ExperienceStore()
        sizes = [len(store)]
        store.append(record("2026-06-19 10:00:00", "2026-06-19 11:00:00"))
        sizes.append(len(store))
        store.append(record("2026-06-19 10:05:00", "2026-06-19 11:05:00"))
        sizes.append(len(store))
        self.assertEqual(sizes, [0, 1, 2])
        self.assertTrue(all(sizes[i] <= sizes[i + 1] for i in range(len(sizes) - 1)))

    def test_f_deterministic_retrieval(self):
        store = ExperienceStore()
        store.append(record("2026-06-19 10:00:00", "2026-06-19 11:00:00", r=None))
        a = store.summary("2026-06-19 12:00:00").to_mapping()
        b = store.summary("2026-06-19 12:00:00").to_mapping()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
