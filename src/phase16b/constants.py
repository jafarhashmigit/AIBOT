"""Phase 16B constants. Does not modify Phase 1–16A."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase16b"
DATA_DIR = SRC_DIR / "data" / "phase16b"

RECIPE_ID = "phase16b_discord_delivery_v1"
SEED = 42

CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
CANDIDATE_STATUS = "EXPERIMENTAL"

# Destination metadata (not secrets). Webhook URL must come from env only.
DISCORD_SERVER_ID = "1569306936757719090"
DISCORD_CHANNEL_ID = "1569306937428803667"
ENV_WEBHOOK_KEY = "DISCORD_WEBHOOK_URL"

HTTP_TIMEOUT_SECONDS = 5.0
HTTP_MAX_ATTEMPTS = 3
HTTP_RETRY_BACKOFF_SECONDS = (0.25, 0.75)

EXPERIMENTAL_DISCLAIMER = "EXPERIMENTAL — NOT A LIVE TRADING SIGNAL"

MESSAGE_TYPES = (
    "WAIT",
    "EXPERIMENTAL_BUY",
    "EXPERIMENTAL_SELL",
    "PILOT_STATUS",
    "ERROR_DELIVERY_FAILURE",
)

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
REAL_DISCORD_SENDS = 0
BUY_SELL_FABRICATED = False

PROTECTED_HASHES = {
    "src/phase16a/constants.py": "428327ae992e8c562b40d255b7f3fb2665f5b0bf77b771354e0e6a157233e926",
    "src/phase16a/predictor.py": "1ff5ffb49fa31a8bc7e1f130ca436f33eb990d97f0afdfafda0c622f06f5e81d",
    "src/phase16a/session.py": "d24ca35a2edd2bcb9f7a2a86ddd7269b9e67566037e0d74019218114c0941f6f",
    "src/phase16a/run_phase16a.py": "aacf3ce8c3ca298b7b43b5054c5c9fd31fee60e35de4a4e0a3fd9ecb9573c131",
    "docs/agent/PHASE_16A_SHADOW_INTEGRATION.md": "1bbca338b454cbe21c5e9db538dc025569d7d7aa069c1979fc3609fa92ce9837",
    "docs/agent/PHASE_16A_PILOT_RESULTS.md": "c2e68baf5fb81253aeb8f484be6b2d04e552eba7997c21b84cf0aea3349e51cb",
    "src/phase14/strategy.py": "68db400ceae47495934b65e464e8f51a593611ef60b5438c09967b59bd76d69b",
    "src/phase6/risk_gate.py": "a9ffbe3429a0800a23e8a1ffee6af5602e7e29e73a612e477c8f6105507df9d3",
    "src/phase12c/gate_adapter.py": "c0b6f20cf8de5b6d3d0096a3627c76a1f134a9890a042cc65bc30c67ad8db1c3",
}
