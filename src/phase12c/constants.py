"""Phase 12C configuration. Independent of Phase 6 mutation. Wait-only remains forced."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF, RISK_GATE_VERSION

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase12c"

ADAPTER_VERSION = "phase12c_forward_gate_adapter_v1"
RECIPE_ID = "phase12c_forward_compatibility_v1"
SEED = 42
SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
SOURCE_FORWARD = "FORWARD_SHADOW"
HOLDOUT_NAME = "xauusd_m5_test.csv"

# Frozen champion for Phase 12C. Not promoted.
CHAMPION_STATUS = "NO_MODEL"
CHAMPION = CHAMPION_ID
PHASE6_RISK_GATE_VERSION = RISK_GATE_VERSION
RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF

# Explicit: full Phase 6 evaluate() on forward Observations is NOT claimed.
FULL_EVALUATE_PARITY = "NOT_PROVEN"
RISK_GATE_APPLY_PARITY_TARGET = "PASS"

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
LIVE_MARKET_REQUESTS = 0
MODEL_TRAINING_RUNS = 0
STAGE_B_AUTHORIZED = False

# Phase 12 / 12B files that must remain unchanged by Phase 12C.
PHASE12_PROTECTED_HASHES = {
    "src/phase12/mt5_readonly.py": "f5ae87c8f9832be8fdfd9a58a753a2fe3261a0637524630eeeb215b887bec3ca",
    "src/phase12/mt5_allowlist.py": "e3bd0c6ad3a08b8ac2f8f7b744cda6bc8d2b2fd9262c6081ba9247a3a50cf6ba",
    "src/phase12/decision_recorder.py": "75460d4c5e11b70789c1bb1f0add3efabccea7ccac3ecf06c56a39e857df6028",
    "src/phase12/session_manager.py": "7534e0ad8214957078925ce0f75f54e3960da76e7bfc0e3ff7ebbf2571aa12ca",
    "src/phase12/storage.py": "78b60d70b311832207cba7adf2d99a37299f53383d426e30e1948cdadaa91fcd",
    "src/phase12/run_phase12.py": "12d0e2e3042ddd534414428de6b7886f25db11a9c241c2bb21df8d32ae190865",
    "src/phase12/parity_audit.py": "fc015e287104cd2115e2712b0144c08f2aa32518f5e59a26cb2c3310381a6654",
    "src/phase12/run_phase12b.py": "aea1564cec0fb2f9c7e52d955dbd0576fd6c6d6e0b49487898e152d0578e0150",
    "src/phase12/tests/test_phase12b.py": "f8cbbef784f9128682772459186d625c296e855d78e2e4fa350428e62c8d348e",
    "docs/agent/PHASE_12B_PREFLIGHT_AUDIT.md": "cb5b4f78b3fd98e5a8870f129f1aa377e5b20761be20320e2b55aa732f556571",
    "reports/phase12b/preflight_summary.json": "605b9d2c520a69231ba3d2dd9cadae4c5b8a337599195a0821655ea23b5ba0b7",
    "reports/phase12b/risk_gate_parity.json": "0e5be6ef3d452a53173afa4ccf1ef4d6dbf31be9afbc005809fe2983edfa9e6d",
    "reports/phase12b/mt5_static_audit.json": "2ecf228f7734177605382420aabed467d1633c6eecb0f18dddffb6a3af740805",
    "reports/phase12b/integrity.json": "fd019bc9008e8676895b6fdbeba8c2439e597ee8751de9f80842d3e71459921f",
}
