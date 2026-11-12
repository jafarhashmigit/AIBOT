"""Phase 18 constants. Does not modify Phase 1–17 protected behavior."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data" / "phase18"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase18"

RECIPE_ID = "phase18_multi_horizon_shadow_learning_v1"
SEED = 42
EXPERIENCE_VERSION = "phase18_exp_v1"

CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
CANDIDATE = "H13_C_H1_PULLBACK"
CANDIDATE_STATUS = "EXPERIMENTAL"
STRATEGY_ID = "H13_C"

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
SOURCE_TYPE = "FORWARD_SHADOW"
SOURCE_HISTORICAL = "HISTORICAL_HYPOTHETICAL"
SOURCE_SHADOW = "AGENT_SHADOW"

BAR_MINUTES = 5
ATR_PERIOD = 14
TP_ATR_MULTIPLE = 1.5
SL_ATR_MULTIPLE = 1.0
POINT_SIZE = 0.01
MIN_SPREAD_POINTS = 15
EXTRA_COST_PER_SIDE = 0.05
SPREAD_FLOOR_USD = MIN_SPREAD_POINTS * POINT_SIZE

# Horizon ids → M5 bars (must match validated methodology; H12 = established 60M).
HORIZONS: dict[str, int] = {
    "H1": 1,
    "H2": 2,
    "H3": 3,
    "H6": 6,
    "H12": 12,
}
HORIZON_LABELS: dict[str, str] = {
    "H1": "5M",
    "H2": "10M",
    "H3": "15M",
    "H6": "30M",
    "H12": "60M",
}
# No validated selection rule yet — do not invent confidence.
SELECTED_HORIZON_POLICY = "NOT_ESTABLISHED"
SELECTED_HORIZON_DISPLAY = "NOT ESTABLISHED"

OUTCOME_PENDING = "PENDING"
OUTCOME_PASS = "PASS"
OUTCOME_FAIL = "FAIL"
OUTCOME_TIMEOUT = "TIMEOUT"
OUTCOME_N_A_WAIT = "N_A_WAIT"

PKT_TZ = "Asia/Karachi"
DAILY_REPORT_LOCAL_TIME = "23:59"

DEFAULT_MAX_CANDLES = 3
DEFAULT_POLL_INTERVAL_SECONDS = 15
DEFAULT_ENABLE_DISCORD = True

EXPERIMENTAL_DISCLAIMER = "EXPERIMENTAL SHADOW SIGNAL — NOT A LIVE TRADING SIGNAL"
SHADOW_BUY_HEADER = "AIBOT SHADOW — EXPERIMENTAL BUY"
SHADOW_SELL_HEADER = "AIBOT SHADOW — EXPERIMENTAL SELL"
SHADOW_WAIT_HEADER = "AIBOT SHADOW — WAIT"
OUTCOME_HEADER = "SHADOW OUTCOME"
DAILY_HEADER = "📊 AIBOT DAILY SHADOW REPORT"
DAILY_FOOTER = "⚠️ Shadow research only — NOT LIVE TRADING"

FORBIDDEN_SIGNAL_PHRASES = (
    "will hit target in",
    "target will hit",
    "guaranteed hit",
    "will definitely hit",
    "will hit TP",
    "will hit SL",
)

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
AUTO_START_DISABLED = True

# Frozen integrity baselines (Phase 16A/16B unchanged; Phase 17 core frozen as of Phase 18 start).
PROTECTED_HASHES = {
    "src/phase16a/constants.py": "428327ae992e8c562b40d255b7f3fb2665f5b0bf77b771354e0e6a157233e926",
    "src/phase16a/predictor.py": "1ff5ffb49fa31a8bc7e1f130ca436f33eb990d97f0afdfafda0c622f06f5e81d",
    "src/phase16a/session.py": "d24ca35a2edd2bcb9f7a2a86ddd7269b9e67566037e0d74019218114c0941f6f",
    "src/phase16a/mt5_reader.py": "b6dd7ed1352dceaaa39925542ff4954508d6f2ebee2778f5e230155442aa0d6e",
    "src/phase16a/run_phase16a.py": "aacf3ce8c3ca298b7b43b5054c5c9fd31fee60e35de4a4e0a3fd9ecb9573c131",
    "src/phase16b/adapter.py": "ffefb4dc2a466770b9a7e769d21bd6f75600d5a3bee2b70d9607e45770475692",
    "src/phase16b/client.py": "48bac377a60ac67cfbcd5a847070bb993049f6f1fd65329ec3586e6ae584d0bb",
    "src/phase16b/dedupe.py": "7b36e3dba2674217bc7632bfa1c17627d66e68275113eded5c025f1e3ba15563",
    "src/phase16b/formatter.py": "9c6585b26a1c6858ad8eb156bf797de1cb213a4586c577e2faad84f40f80fe1a",
    "src/phase16b/secrets.py": "935e341dcdee5b969ae6acdde92ad6c817b234ddaa9244e59857e278e2dad684",
    "src/phase16b/run_phase16b.py": "6561751655ac26bda5f41807f06024cba4a6fd73c9b39242f897703c8032f4bc",
    "src/phase17/constants.py": "e6e17bdf336af35a0b06fd070ec938242090c5488a0c81ffee171dfd3ad2fc29",
    "src/phase17/loop.py": "1ee125694818579f2ba81d0dd7505b5ff59ad4099deb33155cbe5d143f15cc2c",
    "src/phase17/shadow_messages.py": "65a021fe2e7c557412053a8ef24a13e9c66d4435a1d76f35361e63b49b456996",
    "src/phase17/run_phase17.py": "3ec75f6c3b7f2d9e8dbb0786cf480f0b0585ffebcaea0f04e5736a1f7fdb3786",
}
