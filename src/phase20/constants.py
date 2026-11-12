"""Phase 20 constants. Does not modify Phase 16–19 production behavior."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data" / "phase20"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase20"

# Explicit exclusions — never mix these into real AGENT_SHADOW learning.
PHASE18_LIVE_DATA = SRC_DIR / "data" / "phase18"
PHASE19_SYNTHETIC = SRC_DIR / "data" / "phase19" / "PHASE19_SYNTHETIC_TEST"

RECIPE_ID = "phase20_real_mt5_shadow_observation_v1"
SEED = 42

CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
CANDIDATE = "H13_C_H1_PULLBACK"
CANDIDATE_STATUS = "EXPERIMENTAL"
STRATEGY_ID = "H13_C"

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
SOURCE_TYPE = "FORWARD_SHADOW"
SOURCE_SHADOW = "AGENT_SHADOW"
SOURCE_HISTORICAL = "HISTORICAL_HYPOTHETICAL"

SELECTED_HORIZON_DISPLAY = "NOT ESTABLISHED"

SHADOW_DISCLAIMER = "AIBOT SHADOW — NOT A REAL TRADING SIGNAL"
SHADOW_BUY_HEADER = "AIBOT SHADOW — EXPERIMENTAL BUY"
SHADOW_SELL_HEADER = "AIBOT SHADOW — EXPERIMENTAL SELL"
OUTCOME_HEADER = "AIBOT SHADOW OUTCOME"

DEFAULT_MAX_CANDLES = 12
DEFAULT_POLL_INTERVAL_SECONDS = 15

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
AUTO_START_DISABLED = True

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
    "src/phase18/constants.py": "c3e547ff0bb8a4e2a2059f16a3134167abeaa811cf8028c06283bed689fef5e4",
    "src/phase18/loop.py": "c7ad24e4788273f6bbf17264a284bdf69c2d87c4deb98f87115e93a609744a2b",
    "src/phase18/messages.py": "d1834f720c6e9861226a7551d202d677257d3e68eb9718c7c2164c3158d29ad1",
    "src/phase18/outcomes.py": "b4bbfc481606d33a3d5f2cd25422adbb45d5fa68e891b1cdfeac542099d64464",
    "src/phase18/barrier.py": "4db1972b52a47f3b8ef510d62ac1e6fca5763950ca190457271ff275c548f06d",
    "src/phase18/run_phase18.py": "14ff7c4bb7a4cf52a233bd8ccffd8fdc464c9c0c4f7fdc46d04f5e1644d22abe",
    "src/phase18/experience.py": "eab2109d62ec3dd36615395cc70ab39fa9c0bf8b1eb9e055e22b7f103200335c",
    "src/phase18/store.py": "079458f58df8fef99f827ae00fbc5639e10735fe8d32714711492351813e0416",
    "src/phase19/constants.py": "2d69a04c767424305735e5a40ca3ee3632edcef0f1307474da6519a98f756216",
    "src/phase19/pipeline.py": "c7a77ca37c596e04f2902cd32fe7d073b08f69e8977b64f5794ebc2371dfb788",
    "src/phase19/run_phase19.py": "0fef4041c0a84ec7bdcedf7fa64ed9e8794dc828ee4ef84ba4a3ae42af5f41f8",
}
