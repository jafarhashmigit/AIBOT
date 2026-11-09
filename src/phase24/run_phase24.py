"""Phase 24 runner — offline qualification reports (no OCI/MT5/Discord/installs)."""

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
from phase24.arm64 import build_arm64_report
from phase24.constants import FINAL_DECISION, RECIPE_ID, REPORTS_DIR
from phase24.integrity import protected_hashes_report
from phase24.parity import build_data_parity_report
from phase24.providers import provider_qualification


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(redact_secrets(text) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 24 provider & ARM64 qualification")
    parser.add_argument(
        "--refresh-pypi",
        action="store_true",
        help="Optionally refresh ARM64 evidence from PyPI JSON (read-only; no installs).",
    )
    args = parser.parse_args(argv)

    providers = provider_qualification()
    parity = build_data_parity_report()
    arm64 = build_arm64_report(use_network=bool(args.refresh_pypi))
    hashes = protected_hashes_report()

    decision = providers["final_decision"]
    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "24",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "final_decision": decision,
        "constants_final_decision": FINAL_DECISION,
        "selected_provider": None,
        "arm64_status": arm64.get("overall_arm64_status"),
        "parity_overall": parity.get("overall_parity_status"),
        "protected_hashes_all_ok": hashes["all_ok"],
        "recommended_next_phase": (
            "Phase 25 candidate: Dukascopy historical downloader + full MT5 parity window "
            "OR approved paid provider — still no H13_C recalibration until parity gates pass."
        ),
        "note": "No trading edge claimed. No OCI deploy. No threshold changes.",
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(REPORTS_DIR / "provider_qualification.json", providers)
    _write_json(REPORTS_DIR / "data_parity.json", parity)
    _write_json(REPORTS_DIR / "arm64_compatibility.json", arm64)
    _write_json(REPORTS_DIR / "protected_hashes.json", hashes)
    _write_json(REPORTS_DIR / "phase24_summary.json", summary)

    print(
        json.dumps(
            {
                "final_decision": decision,
                "selected_provider": None,
                "algo_parity": (parity.get("comparisons") or {}).get("AlgoSpecial", {}).get("parity_result"),
                "arm64_status": arm64.get("overall_arm64_status"),
                "protected_hashes_all_ok": hashes["all_ok"],
                "mt5_started": False,
                "discord_sent": False,
                "oci_provisioned": False,
                "packages_installed": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
