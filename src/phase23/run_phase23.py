"""Phase 23 runner — offline architecture validation only."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase16b.secrets import redact_secrets
from phase23.constants import RECIPE_ID, REPORTS_DIR
from phase23.providers import provider_comparison
from phase23.validation import (
    architecture_validation,
    docs_present,
    dump_protected_hashes_report,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(redact_secrets(text) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 23 cloud architecture design validation")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run offline architecture validation and write reports (default action).",
    )
    args = parser.parse_args(argv)
    _ = args  # default always validates

    arch = architecture_validation()
    providers = provider_comparison()
    hashes = dump_protected_hashes_report()
    docs = docs_present()

    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "23",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "design_validation_only",
        "final_status": arch["final_status"],
        "docs_present": docs,
        "architecture_validation": arch,
        "note": "Design only — no cloud deploy, no MT5, no Discord, no provider accounts.",
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(REPORTS_DIR / "architecture_validation.json", arch)
    _write_json(REPORTS_DIR / "provider_comparison.json", providers)
    _write_json(REPORTS_DIR / "protected_hashes.json", hashes)
    _write_json(REPORTS_DIR / "phase23_summary.json", summary)

    print(
        json.dumps(
            {
                "final_status": arch["final_status"],
                "provider_selected": None,
                "provider_blocker": providers["provider_blocker"],
                "protected_hashes_all_ok": hashes["all_ok"],
                "frozen_thresholds_intact": hashes["frozen_thresholds_intact"],
                "cloud_deployed": False,
                "mt5_started": False,
                "discord_sent": False,
                "docs_present": docs,
                "unresolved_blocker_count": len(arch["unresolved_blockers"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
