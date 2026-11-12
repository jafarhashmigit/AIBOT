"""Commission evidence boundary — published ≠ account-specific."""

from __future__ import annotations

from typing import Any

from phase64_11.constants import (
    LIVE_ACCOUNT,
    REQUIRES_GENUINE_ACCOUNT_EVENT,
    UNKNOWN,
    canonical_json_sha256,
)


def investigate_commission_boundary(*, n_trade_deals: int = 0) -> dict[str, Any]:
    account_specific = {
        "exists": UNKNOWN,
        "direction": UNKNOWN,
        "unit": UNKNOWN,
        "basis": UNKNOWN,  # per lot / side / round turn
        "account_type_difference": UNKNOWN,
        "xauusdm_commission_bearing": UNKNOWN,
        "embedded_in_spread_or_separate": UNKNOWN,
        "provable_without_genuine_trade": False,
        "status": UNKNOWN,
        "evidence_type": LIVE_ACCOUNT if n_trade_deals == 0 else LIVE_ACCOUNT,
        "n_trade_deals": n_trade_deals,
        "note": (
            "Only balance/credit history present; balance commission=0 is not trade commission proof. "
            "Account-specific commission cannot be proven without a genuine trade deal "
            "(or an explicit account-type configuration record exposing commission)."
        ),
    }

    published = {
        "status": UNKNOWN,
        "value": UNKNOWN,
        "evidence_type": UNKNOWN,
        "mapped_to_trial15_xauusdm": False,
        "note": (
            "Exness publishes multiple models (spread-only vs Raw/Zero with commission). "
            "No in-repo verified mapping from this Trial15 login to a published schedule. "
            "Published MUST NOT auto-label as account-specific verified."
        ),
    }

    classification = REQUIRES_GENUINE_ACCOUNT_EVENT
    reasoning = (
        "No trade deals exist; symbol/account APIs do not expose a commission schedule field; "
        "order_check/order_calc paths are prohibited. Closing account-specific commission "
        "requires a genuine deal (or a future verified account-type config artifact). "
        "External published schedules alone are insufficient without applicability proof."
    )

    out = {
        "dimension": "commission",
        "current_state": UNKNOWN,
        "account_specific": account_specific,
        "published": published,
        "merged": False,
        "classification": classification,
        "reasoning": reasoning,
        "can_close_without_fill": False,
        "next_evidence": (
            "Genuine XAUUSDm trade deal on this account showing commission field, "
            "OR verified broker account-type configuration document binding this login to a schedule"
        ),
        "fabricated": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
