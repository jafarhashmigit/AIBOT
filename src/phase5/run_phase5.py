"""Phase 5 orchestrator: freeze already documented; fetch; audit; NY-SELL only.

Does not append to xauusd_m5.csv, does not open the holdout, does not send orders.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phase3.nplib import (
    GUARD,
    assert_holdout_untouched,
    holdout_status,
    install_guards,
    save,
    sha256_file,
    wrap,
)
from phase5.constants import (
    APPROVED_M5_START,
    DATA_DIR,
    INDEPENDENT_FEATURES,
    INDEPENDENT_OUTCOMES,
    INDEPENDENT_RAW,
    PHASE2_OOS_SHA256,
    RECIPE_ID,
    REPORTS_DIR,
    RESEARCH_CUTOFF,
    SEED,
)
from phase5.fetch_independent_history import fetch
from phase5.independent_data_audit import audit_raw, load_raw
from phase5.reconstruct_sell_outcomes import reconstruct, write_csv
from phase5.replication_evaluation import evaluate


def _sha_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return sha256_file(path)


def main() -> int:
    install_guards()
    GUARD["cutoff"] = RESEARCH_CUTOFF
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    oos = DATA_DIR / "phase2_oos_predictions.csv"
    raw_approved = DATA_DIR / "xauusd_m5.csv"
    oos_hash = _sha_file(oos)
    approved_hash_before = _sha_file(raw_approved)
    if oos_hash != PHASE2_OOS_SHA256:
        print("Phase 2 OOS hash changed; stopping")
        return 1

    fetch_info = fetch()
    save(REPORTS_DIR / "fetch.json",
         wrap("phase5_fetch", "exploratory", {"recipe": RECIPE_ID}, fetch_info, SEED))
    if fetch_info.get("status") != "ok":
        result = {
            "classification": "REPLICATION INCOMPLETE",
            "reason": "INDEPENDENT REPLICATION DATA UNAVAILABLE",
            "fetch": fetch_info,
            "holdout": holdout_status(),
        }
        save(REPORTS_DIR / "replication_results.json",
             wrap("phase5_replication", "exploratory", {"recipe": RECIPE_ID}, result, SEED))
        print("INDEPENDENT REPLICATION DATA UNAVAILABLE", fetch_info)
        assert_holdout_untouched()
        return 0

    rows = load_raw()
    quality = audit_raw(rows)
    save(REPORTS_DIR / "data_quality.json",
         wrap("phase5_data_quality", "confirmatory", {"recipe": RECIPE_ID}, quality, SEED))
    if quality.get("material_quality_problem"):
        result = {
            "classification": "REPLICATION INCOMPLETE",
            "reason": "independent dataset has material quality problems",
            "quality": quality,
        }
        save(REPORTS_DIR / "replication_results.json",
             wrap("phase5_replication", "exploratory", {"recipe": RECIPE_ID}, result, SEED))
        print("REPLICATION INCOMPLETE: quality")
        assert_holdout_untouched()
        return 0

    features, outcomes = reconstruct(rows)
    write_csv(INDEPENDENT_FEATURES, features)
    write_csv(INDEPENDENT_OUTCOMES, outcomes)
    results = evaluate(outcomes, quality_ok=True)
    results["fetch"] = {k: fetch_info[k] for k in fetch_info if k != "rows"}
    results["quality"] = quality
    results["n_feature_rows"] = len(features)
    results["n_ny_sell_rows"] = len(outcomes)
    results["approved_m5_hash_before"] = approved_hash_before
    results["approved_m5_hash_after"] = _sha_file(raw_approved)
    results["approved_file_unchanged"] = approved_hash_before == _sha_file(raw_approved)
    results["phase2_oos_hash"] = oos_hash
    results["max_timestamp_accessed"] = quality.get("latest")
    results["production_ready"] = False
    results["live_ready"] = False
    save(REPORTS_DIR / "replication_results.json",
         wrap("phase5_replication", "exploratory",
              {"recipe": RECIPE_ID, "hypothesis": "exclusive NY session + SELL, approved outcomes"},
              results, SEED))

    assert_holdout_untouched()
    print("holdout", holdout_status())
    print("independent", quality.get("n"), quality.get("earliest"), "->", quality.get("latest"))
    pooled = results["pooled"]
    print("eligible", pooled.get("eligible_observations"), "mean_r", pooled.get("mean_r"),
          "pf", pooled.get("profit_factor"))
    print("blocks", {k: results["blocks"][k].get("mean_r") for k in ("early", "middle", "late")})
    print("boot", results["bootstrap"])
    print("CLASSIFICATION", results["classification"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
