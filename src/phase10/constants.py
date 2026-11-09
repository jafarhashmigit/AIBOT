"""Phase 10 frozen dual-source conventions. Not a trading-rule search."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase10"

RESEARCH_CUTOFF = "2026-09-29 18:50:00"
MAX_ACCESS_TIMESTAMP = "2026-09-29 17:50:00"
HOLDOUT_NAME = "xauusd_m5_test.csv"
SEED = 42
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
RECIPE_ID = "phase10_dual_source_experience_v1"

SOURCE_HISTORICAL = "HISTORICAL_HYPOTHETICAL"
SOURCE_PAPER = "AGENT_PAPER"
ALLOWED_SOURCES = frozenset({SOURCE_HISTORICAL, SOURCE_PAPER})

PHASE2_OOS_PATH = DATA_DIR / "phase2_oos_predictions.csv"
PHASE9_REPLAY_PATH = DATA_DIR / "phase9_replay_log.csv"

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
}

OUTCOME_KEYS = frozenset({
    "realized_R", "realized_r", "actual_net_r", "actual_net_pnl",
    "exit_reason", "outcome_end", "net_r", "net_pnl",
    "simulated_exit_price", "simulated_realized_r", "simulated_net_pnl",
    "hypothetical_buy_net_r", "hypothetical_sell_net_r",
})
