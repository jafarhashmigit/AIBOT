"""Phase 25 runner — Dukascopy acquisition + frozen-tolerance parity."""

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
from phase25.constants import RECIPE_ID, REPORTS_DIR
from phase25.download import download_parity_days
from phase25.integrity import protected_hashes_report
from phase25.live_feed import assess_live_feed
from phase25.parity import evaluate_historical_parity
from phase25.quality import build_data_quality_report


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(redact_secrets(text) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 25 Dukascopy historical parity")
    parser.add_argument("--skip-download", action="store_true", help="Reuse existing raw ticks")
    parser.add_argument("--days", nargs="*", default=None, help="Override parity days YYYY-MM-DD")
    args = parser.parse_args(argv)

    if not args.skip_download:
        download_summary = download_parity_days(days=args.days)
    else:
        download_summary = {"skipped": True}

    # Tolerances already frozen in constants before this evaluation call.
    parity = evaluate_historical_parity()
    quality = build_data_quality_report()
    live = assess_live_feed()
    hashes = protected_hashes_report()

    summary = {
        "recipe_id": RECIPE_ID,
        "phase": "25",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "historical_status": parity["historical_status"],
        "live_status": live["status"],
        "cloud_ready_declared": False,
        "download_summary": download_summary,
        "recommended_next_phase": (
            "If historical FAIL: investigate broker-basis mismatch / side selection; do not recalibrate H13_C. "
            "If PASS but live UNAVAILABLE: keep local MT5 or hybrid for forward shadow; do not declare CLOUD_READY. "
            "Phase 24 provider blocker remains open unless both historical PASS and an approved live path exist."
        ),
        "note": "No trading edge claimed. Historical parity ≠ live/cloud readiness.",
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(REPORTS_DIR / "historical_parity.json", parity)
    _write_json(REPORTS_DIR / "data_quality.json", quality)
    _write_json(REPORTS_DIR / "live_feed_assessment.json", live)
    _write_json(REPORTS_DIR / "protected_hashes.json", hashes)
    _write_json(REPORTS_DIR / "phase25_summary.json", summary)

    print(
        json.dumps(
            {
                "historical_status": parity["historical_status"],
                "live_status": live["status"],
                "cloud_ready_declared": False,
                "reason": parity.get("reason"),
                "protected_hashes_all_ok": hashes["all_ok"],
                "mt5_started": False,
                "discord_sent": False,
                "packages_installed": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
