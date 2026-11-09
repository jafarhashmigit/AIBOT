import unittest

from phase6.model_registry import ModelRegistry, RegistryError, experimental_stub


class RegistryTests(unittest.TestCase):
    def test_experimental_stub_registers(self):
        registry = ModelRegistry()
        record = registry.register(experimental_stub())
        self.assertEqual(record.status, "EXPERIMENTAL")
        self.assertEqual(record.model_id, "no_model")

    def test_production_status_forbidden(self):
        registry = ModelRegistry()
        registry.register(experimental_stub())
        with self.assertRaises(RegistryError):
            registry.set_status("no_model", "PRODUCTION")


if __name__ == "__main__":
    unittest.main()
