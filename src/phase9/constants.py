"""Phase 9 frozen learner constants. Not searched."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase9"
PHASE2_OOS_PATH = DATA_DIR / "phase2_oos_predictions.csv"
PHASE2_OOS_SHA256 = "6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f"

RESEARCH_CUTOFF = "2026-09-29 18:50:00"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
FOLDS = ("WF1", "WF2", "WF3")
HOLDOUT_NAME = "xauusd_m5_test.csv"
SEED = 42
N_BOOT = 2000
RIDGE_ALPHA = 1.0
MIN_EXPERIENCES_PER_SIDE = 100
RECIPE_ID = "phase9_experience_ridge_v1"
POLICY_ID = "P9_EXPERIENCE_RIDGE"

PHASE9_LEARNER_FEATURE_ALLOWLIST = (
    "p_tp_rf_BUY",
    "p_sl_rf_BUY",
    "p_time_rf_BUY",
    "p_tp_rf_SELL",
    "p_sl_rf_SELL",
    "p_time_rf_SELL",
    "pred_r_rf_BUY",
    "pred_r_rf_SELL",
    "pred_r_ridge_BUY",
    "pred_r_ridge_SELL",
    "pred_r_rf_diff",
    "p_tp_rf_diff",
)

OUTCOME_FEATURE_NAMES = (
    "realized_R",
    "realized_r",
    "actual_net_r",
    "actual_net_pnl",
    "exit_reason",
    "hypothetical_buy_net_r",
    "hypothetical_sell_net_r",
    "outcome_end",
    "net_r",
    "net_pnl",
)

PROTECTED_HASHES = {
    "src/data/phase2_oos_predictions.csv": "6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f",
    "src/data/m5_side_outcomes.csv": "35dfe4cc1db8b3bcd98435e4d26692ba2c2a6d3aaa852abce0a4827cc65bff0c",
    "src/data/xauusd_m5_labeled.csv": "d731316e81b322a175077f98322eec7c7523851df4cc77a950f7c6652941ba11",
    "src/phase2/splits.py": "fcbef70fb211def7f307630de54d93bd0363620950de700d3d03f65b5352953e",
    "src/phase6/decision_engine.py": "bae0cc1a0236bc832212eb2b5693159a811264c2b20a0ec9d262d543e3609c9e",
    "src/phase6/risk_gate.py": "a9ffbe3429a0800a23e8a1ffee6af5602e7e29e73a612e477c8f6105507df9d3",
    "src/data/phase8_replay_log.csv": "444dc4702a8c835d2acd8e04f9e30cc37f2530cf4c23733fa384ed6f0beb109b",
    "src/phase8/experience_store.py": "942144d5b327db82a18b4f2a053a269e0a3574134294aaddc6ed311af9808389",
}
