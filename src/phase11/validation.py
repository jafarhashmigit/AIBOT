"""Integrity, expected baselines, and fail-closed helpers. No writes to Phase 1–10."""

from __future__ import annotations

from phase3.nplib import sha256_file
from phase10.constants import MAX_ACCESS_TIMESTAMP, RESEARCH_CUTOFF
from phase10.experience_intelligence import ExperienceIntelligence, load_paper_decisions_from_phase9
from phase10.historical_store import HistoricalExperienceStore, load_completed_historical
from phase10.paper_store import PaperExperienceStore
from phase3.nplib import read_csv_dicts
from phase7.oos_adapter import load_paired
from phase10.constants import PHASE9_REPLAY_PATH
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase11"
RECIPE_ID = "phase11_dual_source_validation_v1"
SEED = 42
MODEL_TRAINING_RUNS = 0
MT5_CONNECTIONS = 0
LIVE_MARKET_CONNECTIONS = 0
BROKER_ORDERS = 0

EXPECTED_HISTORICAL = 36442
EXPECTED_HIST_BUY = 18221
EXPECTED_HIST_SELL = 18221
EXPECTED_HIST_SKIPPED = 26
EXPECTED_PAPER_DECISIONS = 18234
EXPECTED_PAPER_TRADES = 0
EXPECTED_PAPER_OUTCOMES = 0

PROTECTED_HASHES = {
    "src/data/phase2_oos_predictions.csv": "6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f",
    "src/data/m5_side_outcomes.csv": "35dfe4cc1db8b3bcd98435e4d26692ba2c2a6d3aaa852abce0a4827cc65bff0c",
    "src/data/xauusd_m5_labeled.csv": "d731316e81b322a175077f98322eec7c7523851df4cc77a950f7c6652941ba11",
    "src/phase2/splits.py": "fcbef70fb211def7f307630de54d93bd0363620950de700d3d03f65b5352953e",
    "src/phase6/decision_engine.py": "bae0cc1a0236bc832212eb2b5693159a811264c2b20a0ec9d262d543e3609c9e",
    "src/phase6/risk_gate.py": "a9ffbe3429a0800a23e8a1ffee6af5602e7e29e73a612e477c8f6105507df9d3",
    "src/data/phase8_replay_log.csv": "444dc4702a8c835d2acd8e04f9e30cc37f2530cf4c23733fa384ed6f0beb109b",
    "src/phase8/experience_store.py": "942144d5b327db82a18b4f2a053a269e0a3574134294aaddc6ed311af9808389",
    "src/phase9/learner.py": "a697a8191bef1b2a793fc63eb2678b6c777a5f3a2d2ee53261fead1259821d17",
    "src/phase9/run_phase9.py": "e7dbb0a47123a9abd0ae3003c71a1fcc4975e3303655d4c7a7e48b758c8cf4e1",
    "src/phase9/replay.py": "87c5ea48f797a5fa5f2b96d015ca616a16b312fe1a18e2c423f5eac2a532a5ec",
    "src/data/phase9_replay_log.csv": "3570eb1c5f513b4ccc81563fe76f8a7bc142e55b303788098c250729ddbe80d7",
    "src/phase10/historical_store.py": "fe59ece1002f4c495427f1b950e535c46e04674ad518a0efc1ed9454fbe5ac55",
    "src/phase10/paper_store.py": "eee9cc1cc78e7466b6c66315007171587c0cf0d7f7965b460d006f6837c873da",
    "src/phase10/historical_schema.py": "37f9b775ffe2e4749505c038d37f88fbf760b99dc0e367a07f8445d899241e11",
    "src/phase10/paper_schema.py": "ba81092b8d4e6cf977c45fc4ecc9e67536f466dd2ba9bf0d400d2d65ba7f751b",
    "src/phase10/experience_intelligence.py": "a5835381b5b72b3926b02a5d4678b5b83ed8bc2ee8e082e552e3c86cfae712ea",
    "src/phase10/run_phase10.py": "4765d293cdba68355732e6a501a4207232333ff2233465adcaff4e13d19fef62",
    "reports/phase10/architecture_validation.json": "2a9f2a31df9971d8ec74c6617de3a2d520deb1a75ee50d4a7db7b91c6b9258db",
    "reports/phase10/source_separation.json": "61051e5322ab2ee2e8013f3c99960e8aadb412e606c5bb5b9e916f17f9b4b803",
}


class IntegrityError(RuntimeError):
    pass


class ValidationError(RuntimeError):
    pass


def snapshot_protected() -> dict:
    out = {}
    for rel, expected in PROTECTED_HASHES.items():
        path = PROJECT_ROOT / rel
        actual = sha256_file(path) if path.exists() else None
        out[rel] = {
            "expected": expected,
            "actual": actual,
            "unchanged": actual == expected,
            "exists": path.exists(),
        }
        if not path.exists():
            raise IntegrityError(f"HARD FAILURE: protected artifact missing: {rel}")
        if actual != expected:
            raise IntegrityError(f"HARD FAILURE: protected artifact changed: {rel}")
    return out


def load_real_stores() -> dict:
    """Read-only rebuild of Phase 10 stores from approved artifacts. Does not write them back."""
    pairs, eval_rows, oos_integrity = load_paired()
    hist, skipped, max_hist_ts = load_completed_historical(
        pairs, eval_rows, as_of=MAX_ACCESS_TIMESTAMP
    )
    paper = PaperExperienceStore()
    phase9_rows = read_csv_dicts(PHASE9_REPLAY_PATH)
    max_paper_ts = load_paper_decisions_from_phase9(phase9_rows, paper)
    max_ts = max(max_hist_ts, max_paper_ts)
    if max_ts > MAX_ACCESS_TIMESTAMP:
        raise ValidationError(f"HARD FAILURE: timestamp {max_ts} after max access")
    intel = ExperienceIntelligence(hist, paper)
    return {
        "historical": hist,
        "paper": paper,
        "intelligence": intel,
        "skipped": skipped,
        "max_ts": max_ts,
        "oos_integrity": oos_integrity,
        "n_pairs": len(pairs),
        "cutoff": RESEARCH_CUTOFF,
        "as_of": MAX_ACCESS_TIMESTAMP,
    }


def paper_decisions(store: PaperExperienceStore) -> tuple:
    """Read-only view of journaled decisions. Does not copy into another source."""
    return tuple(store._decisions.values())


def historical_records(store: HistoricalExperienceStore) -> tuple:
    return tuple(store._records)
