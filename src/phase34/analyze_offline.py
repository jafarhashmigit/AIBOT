"""Re-run Phase 34 analysis from saved ticks without downloading.

Usage:
  $env:PYTHONPATH='src'
  python -m phase34.analyze_offline
"""

from __future__ import annotations

import json
from pathlib import Path

from phase34.constants import TICKS_DIR, REPORTS_DIR
from phase34.cost_reconciliation import reconcile_costs
from phase34.dst_validation import validate_utc_dst
from phase34.intrabar import analyze_intrabar
from phase34.mt5_parity import report_mt5_parity
from phase34.progress import write_json
from phase34.qualification import finalize
from phase34.quality import validate_ticks
from phase34.spread_analysis import analyze_spreads, independent_recompute_from_jsonl
from phase34.immutability import check_phase33_immutability


def load_all_ticks() -> list[dict]:
    ticks = []
    if not TICKS_DIR.is_dir():
        return ticks
    for path in sorted(TICKS_DIR.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    ticks.append(json.loads(line))
    return ticks


def main() -> dict:
    acq_path = REPORTS_DIR / "acquisition_manifest.json"
    acquisition = json.loads(acq_path.read_text(encoding="utf-8")) if acq_path.is_file() else {}
    ticks = load_all_ticks()
    days = list((acquisition.get("days") or {}).keys()) or sorted({t["timestamp_utc"][:10] for t in ticks})

    quality = validate_ticks(ticks)
    dst = validate_utc_dst(ticks, days)
    spreads = analyze_spreads(ticks)
    paths = sorted(TICKS_DIR.glob("*.jsonl")) if TICKS_DIR.is_dir() else []
    independent = independent_recompute_from_jsonl(paths)
    write_json("independent_spread_recompute.json", independent)
    costs = reconcile_costs(spreads)
    intrabar = analyze_intrabar(ticks, acquisition)
    mt5 = report_mt5_parity()
    immutability = check_phase33_immutability()
    qual = finalize(
        acquisition=acquisition,
        quality=quality,
        dst=dst,
        spreads=spreads,
        costs=costs,
        intrabar=intrabar,
        mt5=mt5,
        immutability=immutability,
        independent=independent,
    )
    print(json.dumps({"final_verdict": qual["final_verdict"], "n_ticks": len(ticks)}, indent=2))
    return qual


if __name__ == "__main__":
    main()
