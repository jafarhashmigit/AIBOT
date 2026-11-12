"""Frozen PROJECT_PREREGISTERED_PARAMETERS for H70_LS1 — not optimized on outcomes."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "completion"
REGISTRY_PATH = PROJECT_ROOT / "reports" / "completion" / "H70_LS1_hypothesis_registry.json"

HYPOTHESIS_ID = "H70_LS1_ASIA_SWEEP_LONDON_MSS"
POLICY_VERSION = "h70_ls1_asia_london_mss_v1"
PARAMETER_LABEL = "PROJECT_PREREGISTERED_PARAMETERS"
SYMBOL = "XAUUSDm"
TIMEFRAME = "M5"

# --- Sessions (IANA, DST-aware) ---
# Asia range: Tokyo cash window. NOT claimed as original creator settings.
ASIA_TZ = "Asia/Tokyo"
ASIA_START_HM = (9, 0)  # inclusive local
ASIA_END_HM = (15, 0)  # exclusive local

# London confirmation window (Europe/London local)
LONDON_TZ = "Europe/London"
LONDON_START_HM = (8, 0)  # inclusive
LONDON_END_HM = (12, 0)  # exclusive — morning confirmation only

# --- Range quality ---
MIN_ASIA_BARS = 24  # at least 2 hours of M5
MIN_ASIA_RANGE_ABS = 0.50  # USD; reject collapsed range
MAX_ASIA_RANGE_ATR = 8.0  # reject absurd spikes vs ATR at Asia end

# --- Sweep ---
SWEEP_BUFFER_ATR = 0.05  # penetration beyond Asia extreme
SWEEP_BUFFER_ABS_MIN = 0.05
REQUIRE_CLOSE_BACK_INSIDE = True
SWEEP_TO_MSS_MAX_BARS = 36  # 3h of M5 after sweep bar

# --- Swing / MSS (closed-bar fractal; no repaint) ---
SWING_LEFT = 2
SWING_RIGHT = 2  # swing at i confirmed only when bar i+SWING_RIGHT is closed

# --- Entry / risk product rules (engineering defaults; NOT validated edge) ---
REWARD_RISK = 2.0
MIN_REWARD_RISK = 1.5
SL_BUFFER_ATR = 0.05
SL_BUFFER_ABS_MIN = 0.05
SIGNAL_EXPIRY_BARS = 3  # signal age after MSS confirmation bar
MAX_HOLD_BARS = 48

# Safety posture (policy never authorizes broker)
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
ORDER_SEND = "PROHIBITED"
BROKER_COLLECTION = "READ_ONLY"
