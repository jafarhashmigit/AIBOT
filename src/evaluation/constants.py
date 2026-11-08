"""Shared constants for the Phase 1 evaluation framework.

Nothing here changes the existing label, cost or backtest rules. Values are
copied from the scripts that already own them (label_m5, train_rf_m5,
research_m5_label_horizon, ACCEPTANCE_CRITERIA.md).
"""

from pathlib import Path

from features_m5 import BAR_MINUTES
from label_m5 import HORIZON_BARS, PURGE_BARS

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
MODELS_DIR = SRC_DIR / "models"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase1"

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# Research cutoff = last validation bar + 12-bar purge (inside the gap before the test split).
# Server clock. Never read a price row after this stamp.
RESEARCH_CUTOFF = "2026-09-29 18:50:00"
VALIDATION_END = "2026-09-29 17:50:00"

# Existing M5 walk-forward windows (row-fraction 0.55 / 0.70 / 0.85 of research feature rows).
WF_BOUNDARY_FRACTIONS = (0.55, 0.70, 0.85)
EXPECTED_WF_WINDOWS = [
    ("2026-06-19 03:05:00", "2026-07-23 11:25:00"),
    ("2026-07-23 11:25:00", "2026-08-26 13:55:00"),
    ("2026-08-26 13:55:00", "2026-09-29 17:50:00"),
]

DEFAULT_SEED = 42
PURGE_BARS_M5 = PURGE_BARS  # 12
HORIZON_BARS_M5 = HORIZON_BARS  # 12
BAR_MINUTES_M5 = BAR_MINUTES  # 5

# Published RF validation backtest figures (backtest_rf_m5 report, rounded).
# Exact comparison uses the saved trades CSV, not these rounded values.
RF_VALIDATION_PUBLISHED = {
    "trades": 1518,
    "net_pnl": -162.66,
    "avg_r": -0.0169,
    "profit_factor": 0.965,
    "max_drawdown_usd": 389.95,
}

# G2 thresholds from docs/agent/ACCEPTANCE_CRITERIA.md (pre-registered, frozen).
G2 = {
    "min_pooled_trades": 300,
    "min_trades_per_block": 50,
    "min_mean_r": 0.05,
    "min_positive_blocks_3": 2,
    "min_positive_blocks_frac": 0.75,
    "worst_block_r": -0.10,
    "min_profit_factor": 1.10,
    "min_block_profit_factor": 0.90,
    "bootstrap_samples": 2000,
    "bootstrap_seed": 42,
    "ci_lower_must_exceed": 0.0,
    "bootstrap_p_mean_le_0": 0.025,
    "permutation_a_draws": 200,
    "permutation_b_draws": 1000,
    "fdr_q": 0.10,
    "max_drawdown_r": 20.0,
    "min_total_r_over_dd": 1.0,
    "max_block_r_share": 0.50,
}

# Historical reproduction uses the original iid trade bootstrap (E12).
# G2 uses a day-clustered / moving-block bootstrap. They are different estimators;
# do not mix them when comparing to saved E12 figures.
IID_TRADE_BOOT_SAMPLES = 2000
IID_TRADE_BOOT_SEED = 42
DAY_BLOCK_BOOT_SAMPLES = 2000
DAY_BLOCK_BOOT_SEED = 42

# Finding class for reports.
EXPLORATORY = "exploratory"
CONFIRMATORY = "confirmatory"
REPRODUCTION = "reproduction"
