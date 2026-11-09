"""Phase 23 design-only constants. Does not modify Phase 16A–22."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase23"

RECIPE_ID = "phase23_cloud_architecture_design_v1"
FINAL_STATUS = "CLOUD_ARCHITECTURE_READY_WITH_PROVIDER_BLOCKER"

CHAMPION_STATUS = "NO_MODEL"
CANDIDATE_STATUS = "EXPERIMENTAL"
PRODUCTION_FINAL_ACTION = "WAIT"
BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
GITHUB_PUSH = False
CLOUD_DEPLOYED = False
PROVIDER_SELECTED = None

# Design target (Oracle Always Free Ampere A1 as of late-2026 docs).
OCI_SHAPE = "VM.Standard.A1.Flex"
OCI_OCPUS = 2
OCI_MEMORY_GB = 12
OCI_BLOCK_STORAGE_GB_TOTAL = 200

# Components required by architecture (design checklist).
REQUIRED_COMPONENTS = [
    "MarketDataProvider",
    "IndependentXAUUSDAdapter",
    "UTCTimestampNormalization",
    "M5CandleBuilderValidator",
    "DuplicateMissingCandleDetection",
    "MarketDataHealthMonitor",
    "ObservationPredictionPipeline",
    "RiskGateWaitOnly",
    "PersistentDecisionOutcomeJournal",
    "SeparatedExperienceStores",
    "DiscordNotificationAdapter",
    "ProcessSupervisorHealthRestart",
]

# Providers evaluated from public documentation only (no live contact).
PROVIDER_CANDIDATES = [
    "AlgoSpecial",
    "TickFeed",
    "TwelveData_Basic",
    "Finnhub_Free",
    "biquote",
    "V2BOT",
    "Local_MT5_reference_only",
]

# ARM64 risk inventory from requirements.txt pins (Windows x64 verified historically).
ARM64_RISKS = {
    "MetaTrader5==5.0.6231": "BLOCKER_for_linux_arm64_cloud_runtime",
    "numpy==2.5.4": "VERIFY_aarch64_wheel",
    "pandas==3.1.1": "VERIFY_aarch64_wheel",
    "scipy==1.18.1": "VERIFY_aarch64_wheel",
    "scikit-learn==1.9.1": "VERIFY_aarch64_wheel",
    "joblib==1.6.0": "LOW_pure_python_likely",
    "tzdata==2026.6": "LOW",
}
