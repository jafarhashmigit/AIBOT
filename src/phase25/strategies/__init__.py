"""Independent experimental strategies for Phase 25."""

from phase25.strategies.breakout_retest import decide_breakout_retest
from phase25.strategies.mean_reversion import decide_mean_reversion
from phase25.strategies.mtf_h1_m5 import decide_mtf_h1_m5
from phase25.strategies.regime_router import decide_regime_router
from phase25.strategies.smc_liquidity import decide_smc_liquidity

STRATEGIES = {
    "mean_reversion": decide_mean_reversion,
    "breakout_retest": decide_breakout_retest,
    "smc_liquidity": decide_smc_liquidity,
    "regime_router": decide_regime_router,
    "mtf_h1_m5": decide_mtf_h1_m5,
}
