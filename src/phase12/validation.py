"""Integrity and fail-closed helpers. Stage A never opens MT5."""

from __future__ import annotations

from pathlib import Path

from phase3.nplib import sha256_file
from phase6.constants import CHAMPION_ID, RISK_GATE_VERSION
from phase6.risk_gate import RiskGate

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data" / "phase12"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase12"
RECIPE_ID = "phase12_forward_shadow_v1"
SEED = 42
SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
HORIZON_BARS = 12
BAR_MINUTES = 5
HORIZON_MINUTES = HORIZON_BARS * BAR_MINUTES
SOURCE_FORWARD = "FORWARD_SHADOW"
SOURCE_HISTORICAL = "HISTORICAL_HYPOTHETICAL"
SOURCE_PAPER = "AGENT_PAPER"
CHAMPION = CHAMPION_ID
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
HOLDOUT_NAME = "xauusd_m5_test.csv"

MT5_CONNECTIONS = 0
LIVE_MARKET_REQUESTS = 0
BROKER_ORDERS = 0
MODEL_TRAINING_RUNS = 0
BACKGROUND_PROCESSES = 0
SCHEDULED_TASKS = 0

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
    "src/phase10/run_phase10.py": "4765d293cdba68355732e6a501a4207232333ff2233465adcaff4e13d19fef62",
    "reports/phase10/architecture_validation.json": "2a9f2a31df9971d8ec74c6617de3a2d520deb1a75ee50d4a7db7b91c6b9258db",
    "src/phase11/historical_audit.py": "7f1e13f20662a639711dfeef5cb530587ab59ca05c27eacb8e655a21d3a64e9a",
    "src/phase11/paper_audit.py": "5c510dadc2bd3ede102f305332fe8c97730cc1d53f3156514ba73671d18b7d52",
    "src/phase11/run_phase11.py": "54607574b6f992c0b979f482d506099aec75ae9c55790eba2f4bece474558743",
    "reports/phase11/historical_validation.json": "32c8b0a91d1f32547f6859b0b277be64d84aec0b4abec59a019ab87071606f8f",
    "reports/phase11/paper_validation.json": "2dd468f3ab38888658d2d70ba520e2772359b238db239d3ed83e078873bca131",
    "reports/phase11/source_compatibility.json": "fd9913c734b47d262b5708b947d09732e3e5b834a521caa470ddf02fc8b96011",
}


class IntegrityError(RuntimeError):
    pass


class ShadowError(ValueError):
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


def frozen_risk_gate() -> RiskGate:
    gate = RiskGate()
    if not gate.wait_only or gate.champion_id != CHAMPION or gate.version != RISK_GATE_VERSION:
        raise IntegrityError("HARD FAILURE: Phase 6 RiskGate defaults changed")
    return gate


def assert_no_broker_in_text(text: str) -> None:
    lowered = text.lower()
    for name in ("order_send", "order_close", "place_order", "send_order", "order_calc"):
        if name in lowered:
            raise ShadowError(f"broker surface referenced: {name}")
