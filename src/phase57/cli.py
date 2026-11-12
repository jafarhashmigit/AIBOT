"""Phase57 CLI — validation only; never auto-starts."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase57 autonomous reliability validation (CLI only)")
    p.add_argument("--run", action="store_true", help="Execute full validation suite and write reports")
    p.add_argument("--tests-only", action="store_true", help="Run unittest suite only")
    args = p.parse_args(argv)
    if not args.run and not args.tests_only:
        p.print_help()
        return 2
    if args.tests_only:
        import unittest

        suite = unittest.defaultTestLoader.loadTestsFromName("phase57.tests.test_phase57")
        ok = unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()
        return 0 if ok else 1
    from phase57.run_phase57 import main as run_main

    return run_main()


if __name__ == "__main__":
    sys.exit(main())
