"""CLI: Phase 29 historical 500-candle diagnostic (research only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase29.historical_diagnostic import (  # noqa: E402
    DIAG_N,
    run_historical_500_diagnostic,
    write_historical_reports,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 29 HISTORICAL_DIAGNOSTIC_ONLY 500-candle backtest")
    p.add_argument("--n", type=int, default=DIAG_N)
    p.add_argument("--no-high-only", action="store_true")
    p.add_argument("--write-reports", action="store_true", default=True)
    p.add_argument("--no-write-reports", action="store_true")
    args = p.parse_args(argv)

    report = run_historical_500_diagnostic(
        n=args.n,
        include_high_only=not args.no_high_only,
    )
    write = args.write_reports and not args.no_write_reports
    paths = write_historical_reports(report) if write else {}
    summary = {
        "label": report["label"],
        "not_forward_validation": report["not_forward_validation"],
        "window": report["window"],
        "baseline_counts": report["baseline_h13c"]["counts"],
        "baseline_h12": report["baseline_h13c"]["performance_h12"]["combined"],
        "high_only_counts": report["high_only_research"]["counts"],
        "holdout_accessed": report["holdout"]["accessed"],
        "production": report["verdict_channels"]["PRODUCTION_STATUS"],
        "edge_claim": report["edge_claim"],
        "reports": {k: str(v) for k, v in paths.items()},
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
