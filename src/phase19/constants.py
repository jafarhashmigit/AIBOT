"""Phase 19 constants. Does not modify Phase 16–18 production behavior."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data" / "phase19"
SYNTHETIC_NAMESPACE = "PHASE19_SYNTHETIC_TEST"
SYNTHETIC_ROOT = DATA_DIR / SYNTHETIC_NAMESPACE
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase19"

RECIPE_ID = "phase19_shadow_outcome_pipeline_validation_v1"
SEED = 42

CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
CANDIDATE = "H13_C_H1_PULLBACK"
CANDIDATE_STATUS = "EXPERIMENTAL"
STRATEGY_ID = "H13_C"

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
SOURCE_SYNTHETIC = "PHASE19_SYNTHETIC_TEST"
SOURCE_SHADOW = "AGENT_SHADOW"
SOURCE_HISTORICAL = "HISTORICAL_HYPOTHETICAL"

SYNTHETIC_SIGNAL_BANNER = "PHASE 19 SYNTHETIC TEST"
SYNTHETIC_NOT_REAL = "NOT A REAL TRADING SIGNAL"
SYNTHETIC_OUTCOME_BANNER = "PHASE 19 SYNTHETIC OUTCOME"
SYNTHETIC_DAILY_BANNER = "PHASE 19 SYNTHETIC DAILY REPORT"

FORBIDDEN_PHRASES = (
    "will hit target in",
    "target will hit",
    "guaranteed hit",
    "will definitely hit",
    "target will definitely hit in",
)

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
AUTO_START_DISABLED = True
PRODUCTION_DATA_TOUCHED = False

# Frozen integrity baselines — Phase 16A/16B/17/18 production sources must remain unchanged.
PROTECTED_HASHES = {
    "src/phase16a/constants.py": "428327ae992e8c562b40d255b7f3fb2665f5b0bf77b771354e0e6a157233e926",
    "src/phase16a/predictor.py": "1ff5ffb49fa31a8bc7e1f130ca436f33eb990d97f0afdfafda0c622f06f5e81d",
    "src/phase16a/session.py": "d24ca35a2edd2bcb9f7a2a86ddd7269b9e67566037e0d74019218114c0941f6f",
    "src/phase16a/mt5_reader.py": "b6dd7ed1352dceaaa39925542ff4954508d6f2ebee2778f5e230155442aa0d6e",
    "src/phase16a/run_phase16a.py": "aacf3ce8c3ca298b7b43b5054c5c9fd31fee60e35de4a4e0a3fd9ecb9573c131",
    "src/phase16b/adapter.py": "ffefb4dc2a466770b9a7e769d21bd6f75600d5a3bee2b70d9607e45770475692",
    "src/phase16b/client.py": "48bac377a60ac67cfbcd5a847070bb993049f6f1fd65329ec3586e6ae584d0bb",
    "src/phase16b/dedupe.py": "7b36e3dba2674217bc7632bfa1c17627d66e68275113eded5c025f1e3ba15563",
    "src/phase16b/formatter.py": "d68098a1120e8f31b28ece2c564a0856cdb6eacd61606e3b0de50d403191dc83",
    "src/phase16b/secrets.py": "935e341dcdee5b969ae6acdde92ad6c817b234ddaa9244e59857e278e2dad684",
    "src/phase16b/run_phase16b.py": "6561751655ac26bda5f41807f06024cba4a6fd73c9b39242f897703c8032f4bc",
    "src/phase17/constants.py": "f2a313325d1cb63e78c13388ca326eed94e9c3654af433f07f2b9ccf67504ebd",
    "src/phase17/loop.py": "1ee125694818579f2ba81d0dd7505b5ff59ad4099deb33155cbe5d143f15cc2c",
    "src/phase17/shadow_messages.py": "eb7af910551da2119ce0d89582e3c73e86acc48f9f948fbddb1b09e64fb8e69b",
    "src/phase17/run_phase17.py": "3ec75f6c3b7f2d9e8dbb0786cf480f0b0585ffebcaea0f04e5736a1f7fdb3786",
    "src/phase18/constants.py": "a740d2c46a48725d5eb7532a322c443f6af597ec691ccaaaf61e8007350769b8",
    "src/phase18/loop.py": "c7ad24e4788273f6bbf17264a284bdf69c2d87c4deb98f87115e93a609744a2b",
    "src/phase18/messages.py": "7c78a6a188368b5011bb5b85c39ca9d0d52e5fbfb0f3e247b3822238a9817311",
    "src/phase18/outcomes.py": "b4bbfc481606d33a3d5f2cd25422adbb45d5fa68e891b1cdfeac542099d64464",
    "src/phase18/barrier.py": "4db1972b52a47f3b8ef510d62ac1e6fca5763950ca190457271ff275c548f06d",
    "src/phase18/run_phase18.py": "14ff7c4bb7a4cf52a233bd8ccffd8fdc464c9c0c4f7fdc46d04f5e1644d22abe",
}
