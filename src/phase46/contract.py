"""Frozen research contract — hashed before any outcome evaluation."""

from __future__ import annotations

from typing import Any

from phase46.constants import (
    ATR_PERIOD,
    ENGINEERING_DATES,
    FORBIDDEN_VALIDATION_DATES,
    HORIZON_BARS,
    RECIPE_ID,
    RETIRED_DO_NOT_REVIVE,
    SOURCE_SERVER_LABEL,
    SYMBOL,
    canonical_json_sha256,
)
from phase46.cost_scenarios import COST_SCENARIO_REGISTRY


def build_research_contract() -> dict[str, Any]:
    """Freeze target / execution / cost / data rules. No post-hoc threshold edits."""
    contract: dict[str, Any] = {
        "recipe_id": RECIPE_ID,
        "purpose": (
            "Define action-conditioned, bid/ask-aware gross and net R outcomes "
            "for BUY/SELL/WAIT as the M1 foundation. Not a profitability claim."
        ),
        "target_definition": {
            "primary": "net_R under named cost scenario s",
            "gross": "gross_R = gross_pnl / risk_amount",
            "net": (
                "EV_net(a|x,s) = EV_gross(a|x) - E[cost_R|x,a,s] "
                "when costs are applied as ADDITIVE scenarios; "
                "if a field already embeds bid/ask spread, do not subtract observed spread again"
            ),
            "wait": "WAIT has gross_pnl=0, all costs=0, net_R=0 (no opportunity-cost model in Phase46)",
            "not_a_target": "mid-price directional sign(r) is not the Phase46 primary target",
        },
        "entry_exit_conventions": {
            "decision_bar": "Completed M5 bar i (timestamp_utc open time of bar)",
            "entry_bar": "Next eligible M5 bar i+1",
            "BUY_entry": "First tick ASK on entry bar",
            "BUY_exit": "Last tick BID on exit bar (horizon end)",
            "SELL_entry": "First tick BID on entry bar",
            "SELL_exit": "Last tick ASK on exit bar (horizon end)",
            "mid_price_fills": "FORBIDDEN — never silent mid substitution",
            "forming_h1": "NOT USED — M5 + ticks only; no forming H1 features",
        },
        "horizons": {
            "unit": "M5 bars",
            "horizon_bars": HORIZON_BARS,
            "exit_reason_primary": "HORIZON_EXIT",
            "volatility_time": "NOT USED in Phase46 (fixed bar horizon frozen)",
        },
        "risk_normalization": {
            "risk_amount": f"ATR({ATR_PERIOD}) of completed M5 bars ending at decision bar i",
            "atr_inputs": "high/low/close of bars <= i only (no lookahead into entry/exit bars)",
            "gross_R": "gross_pnl / risk_amount",
            "net_R": "net_pnl / risk_amount",
            "invalid_if": "ATR missing or <= 0 → data_quality_status=INVALID_RISK; excluded from EV means",
        },
        "execution_assumptions": {
            "source": SOURCE_SERVER_LABEL,
            "symbol": SYMBOL,
            "live_broker_truth": False,
            "demo_note": "MetaQuotes-Demo bid/ask is reconstruction substrate, not live execution truth",
            "commission_base": "UNKNOWN — not invented",
            "slippage_base": "UNKNOWN — not invented",
            "observed_spread": "Embedded in bid/ask fills; reported separately; not double-subtracted in OBSERVED_BIDASK_ONLY",
        },
        "missing_data_rules": {
            "missing_entry_ticks": "MISSING_ENTRY_TICKS — no fabricated prices",
            "missing_exit_ticks": "MISSING_EXIT_TICKS",
            "incomplete_horizon": "INCOMPLETE_HORIZON",
            "invalid_quote": "ask < bid skipped in tick index; if no valid ticks → missing",
            "empty_session_hour": "Treated as genuinely empty only if file exists with 0 rows or absent hour files with explicit status",
        },
        "cost_scenarios": COST_SCENARIO_REGISTRY,
        "evaluation_metrics": [
            "mean_gross_R",
            "mean_net_R",
            "median_net_R",
            "win_rate_net_R_gt_0",
            "profit_factor_net",
            "max_drawdown_net_R_path",
            "trade_count",
            "exposure_max_concurrent",
            "date_block_bootstrap_ci95_mean_net_R",
            "cost_sensitivity_across_scenarios",
        ],
        "baselines_diagnostic_only": [
            "ALWAYS_WAIT",
            "UNCONDITIONAL_BUY",
            "UNCONDITIONAL_SELL",
            "ALTERNATING_BUY_SELL",
        ],
        "data_exposure": {
            "engineering_dates": ENGINEERING_DATES,
            "engineering_label": "PHASE44_DISCOVERY_ALREADY_EXPOSED — exploratory/engineering only",
            "forbidden_validation_dates": sorted(FORBIDDEN_VALIDATION_DATES),
            "holdout_legacy": "FORBIDDEN",
            "independent_validation_claim": "NOT CLAIMED — engineering dates are not independent",
            "new_mt5_downloads": False,
            "live_forward_mt5": False,
        },
        "retired_hypotheses_do_not_revive": list(RETIRED_DO_NOT_REVIVE),
        "out_of_scope": [
            "neural_networks",
            "reinforcement_learning",
            "contextual_bandits",
            "online_policy_updates",
            "strategy_discovery",
            "new_indicator_combinations",
            "live_trading",
            "model_promotion",
        ],
        "threshold_policy": (
            "No acceptance thresholds for 'edge found' exist in Phase46. "
            "No metric thresholds may be adjusted after inspecting evaluation results."
        ),
        "champion": "NO_MODEL",
        "production": "WAIT",
    }
    contract["contract_sha256"] = canonical_json_sha256(
        {k: v for k, v in contract.items() if k != "contract_sha256"}
    )
    return contract
