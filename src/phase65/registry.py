"""Preregistered Phase65 hypotheses — freeze before evaluation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase65.constants import (
    BONFERRONI_N,
    DO_NOT_REPEAT,
    HYPOTHESIS_BUDGET,
    REGISTRY_PATH,
    canonical_json_sha256,
)


def _hypotheses() -> list[dict[str, Any]]:
    ts = "2026-11-12T00:00:00Z"  # fixed for determinism at preregistration
    return [
        {
            "id": "H65_V1_ATR_REGIME_ABSTAIN",
            "version": "v1",
            "created_utc": ts,
            "family": "volatility_regime_abstention",
            "economic_rationale": (
                "Elevated realized ATR relative to recent distribution marks unstable "
                "cost/edge regimes; abstain (WAIT). Otherwise follow 2-bar mid momentum."
            ),
            "mathematical_definition": (
                "Let atr_t = ATR(14) at decision bar. Let q = empirical q80 of atr on discovery "
                "events. If atr_t >= q → WAIT. Else if mid_ret_2bar > 0 → BUY elif < 0 → SELL else WAIT."
            ),
            "features": ["atr", "ret_2bar_mid"],
            "parameters": {"atr_quantile": 0.80, "fitted_on": "discovery_only"},
            "action_rule": "atr_regime_abstain_then_2bar_sign",
            "entry": "next M5 bar first tick (BUY ask / SELL bid)",
            "exit": "horizon 12 M5 bars last tick (BUY bid / SELL ask)",
            "max_holding_horizon_bars": 12,
            "expected_failure": "ATR quantile gate overfits; momentum sign has no incremental value",
            "cost_assumptions": "bid/ask path only; commission/swap UNKNOWN not set to zero",
            "statistical_test": "date_block_bootstrap_mean_net_r_all_decisions",
            "multiple_testing_family": f"H65_budget_{HYPOTHESIS_BUDGET}",
            "bonferroni_n": BONFERRONI_N,
            "min_trades": 15,
            "rejection_criteria": [
                "mean_all <= WAIT",
                "bonferroni_ci_not_exclude_0",
                "insufficient_trades",
                "validation_fails",
            ],
            "not_a_revival_of": ["H58_I1_INACTIVITY_WAIT", "H58_W1_COSTLY_SPREAD_WAIT", "H42_G"],
        },
        {
            "id": "H65_C1_COMPRESSION_EXPANSION",
            "version": "v1",
            "created_utc": ts,
            "family": "compression_expansion",
            "economic_rationale": (
                "Low recent range compression followed by expansion bar may contain directional "
                "displacement; take sign of expansion bar mid-return; else WAIT."
            ),
            "mathematical_definition": (
                "compression = (high-low)/ATR over last 6 completed bars mean. If compression "
                "<= discovery q25 AND abs(ret_1bar_mid) >= discovery median abs ret → follow "
                "sign(ret_1bar_mid); else WAIT."
            ),
            "features": ["range_compression", "ret_1bar_mid", "atr"],
            "parameters": {"compression_q": 0.25, "fitted_on": "discovery_only"},
            "action_rule": "compression_then_expansion_sign",
            "entry": "next M5 bar first tick",
            "exit": "horizon 12 M5",
            "max_holding_horizon_bars": 12,
            "expected_failure": "Compression/expansion is noise on M5 gold demo",
            "cost_assumptions": "bid/ask only; unknown costs stressed separately",
            "statistical_test": "date_block_bootstrap_mean_net_r_all_decisions",
            "multiple_testing_family": f"H65_budget_{HYPOTHESIS_BUDGET}",
            "bonferroni_n": BONFERRONI_N,
            "min_trades": 15,
            "rejection_criteria": [
                "mean_all <= WAIT",
                "bonferroni_ci_not_exclude_0",
                "insufficient_trades",
                "validation_fails",
            ],
            "not_a_revival_of": ["H44_2", "H_B*", "mean_reversion"],
        },
        {
            "id": "H65_S1_SESSION_OPEN_FILTER",
            "version": "v1",
            "created_utc": ts,
            "family": "session_conditioned_momentum",
            "economic_rationale": (
                "New entries only when Exness-published session state is OPEN; during "
                "CLOSE_ONLY/BREAK/CLOSED/UNKNOWN force WAIT. When OPEN, follow 1-bar mid sign."
            ),
            "mathematical_definition": (
                "If session_state != OPEN → WAIT. Else BUY if ret_1bar_mid>0 else SELL if <0 else WAIT."
            ),
            "features": ["session_state", "ret_1bar_mid"],
            "parameters": {"session_source": "phase64_13_exness_schedule"},
            "action_rule": "session_open_then_1bar_sign",
            "entry": "next M5 bar first tick; rejected if session not OPEN",
            "exit": "horizon 12 M5",
            "max_holding_horizon_bars": 12,
            "expected_failure": (
                "Exness schedule on MetaQuotes archive is a proxy; filter may just thin sample"
            ),
            "cost_assumptions": "bid/ask only",
            "statistical_test": "date_block_bootstrap_mean_net_r_all_decisions",
            "multiple_testing_family": f"H65_budget_{HYPOTHESIS_BUDGET}",
            "bonferroni_n": BONFERRONI_N,
            "min_trades": 15,
            "rejection_criteria": [
                "mean_all <= WAIT",
                "bonferroni_ci_not_exclude_0",
                "insufficient_trades",
                "validation_fails",
            ],
            "not_a_revival_of": ["H58_W1_COSTLY_SPREAD_WAIT"],
            "substrate_limitation": "Archive=MetaQuotes-Demo; schedule=Exness UTC XAUUSD/XAUUSDm",
        },
    ]


def build_and_freeze_registry(*, discovery_days: list[str], validation_days: list[str]) -> dict[str, Any]:
    hyps = _hypotheses()
    assert len(hyps) <= HYPOTHESIS_BUDGET
    overlap = [h["id"] for h in hyps if h["id"] in DO_NOT_REPEAT]
    body = {
        "preregistered": True,
        "frozen_before_evaluation": True,
        "n": len(hyps),
        "hypothesis_budget": HYPOTHESIS_BUDGET,
        "hypotheses": hyps,
        "discovery_dataset": discovery_days,
        "validation_dataset": validation_days,
        "holdout_policy": "phase58_holdout_sealed_unless_survivor",
        "forbidden_id_collisions": overlap,
        "commission_slippage_swap": "UNKNOWN_not_invented_as_zero",
        "champion_implication": "NO_MODEL_unless_all_gates",
        "production_implication": "WAIT",
    }
    assert not overlap, overlap
    body["registry_sha256"] = canonical_json_sha256({k: v for k, v in body.items() if k != "registry_sha256"})
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Immutable freeze: if exists with different hash, require new version (tests check)
    if REGISTRY_PATH.is_file():
        prev = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        if prev.get("registry_sha256") == body["registry_sha256"]:
            return prev
        # Same IDs/version freeze — return existing to preserve immutability
        if prev.get("frozen_before_evaluation"):
            return prev
    REGISTRY_PATH.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    body["frozen_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    REGISTRY_PATH.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return body


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        raise FileNotFoundError("hypothesis_registry_not_frozen")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
