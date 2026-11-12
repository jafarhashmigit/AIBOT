"""Account-specific Exness commission model — refuses UNKNOWN-adjusted performance."""

from __future__ import annotations

from typing import Any

from phase61.constants import canonical_json_sha256

# Published investigation references (NOT active unless account verified)
PUBLISHED_XAUUSD_REFERENCE = {
    "Raw Spread": {"usd_per_lot_per_side": 3.5, "source": "commodities_help"},
    "Zero": {"usd_per_lot_per_side": 5.5, "source": "commodities_help"},
    "Standard": {"usd_per_lot_per_side": 0.0, "source": "commission_fee_help", "commission_free": True},
    "Standard Cent": {"usd_per_lot_per_side": 0.0, "source": "commission_fee_help", "commission_free": True},
    "Pro": {"usd_per_lot_per_side": 0.0, "source": "commission_fee_help", "commission_free": True},
}


class ExnessCommissionModel:
    """Supports per-side / round-turn / partial closes once VERIFIED."""

    def __init__(self, calibration: dict[str, Any]):
        self.calibration = calibration
        self.status = calibration.get("commission_status", "UNKNOWN")
        self.schedule = calibration.get("verified_schedule")

    def _per_side_rate(self) -> float | None:
        if self.status != "VERIFIED" or not self.schedule:
            return None
        if self.schedule.get("usd_per_lot_per_side") is not None:
            return float(self.schedule["usd_per_lot_per_side"])
        if self.schedule.get("usd_per_lot_round_turn") is not None:
            return float(self.schedule["usd_per_lot_round_turn"]) / 2.0
        return None

    def commission_for_volume(
        self,
        *,
        lots: float | None,
        sides: int = 1,
        account_currency: str | None = None,
        fx_to_account: float | None = None,
    ) -> float | None:
        if self.status != "VERIFIED":
            return None
        if lots is None or lots < 0:
            return None
        rate = self._per_side_rate()
        if rate is None:
            return None
        usd = rate * float(lots) * int(sides)
        sched_ccy = (self.schedule or {}).get("currency") or "USD"
        if account_currency and account_currency != sched_ccy:
            if fx_to_account is None:
                return None  # refuse silent FX assumption
            return usd * float(fx_to_account)
        return usd

    def entry_and_exit_commission(
        self,
        *,
        entry_lots: float,
        exit_lots: float | None = None,
        charge_both_at_open: bool | None = None,
    ) -> dict[str, Any]:
        """Exness docs: commission for open+close charged as order is opened (when applicable)."""
        if self.status != "VERIFIED":
            return {"status": "UNKNOWN", "total": None, "entry": None, "exit": None}
        both_at_open = charge_both_at_open
        if both_at_open is None:
            both_at_open = bool((self.schedule or {}).get("charge_round_turn_at_open", True))
        exit_lots = entry_lots if exit_lots is None else exit_lots
        if both_at_open:
            total = self.commission_for_volume(lots=entry_lots, sides=2)
            return {
                "status": "VERIFIED",
                "accounting": "round_turn_charged_at_open",
                "entry": total,
                "exit": 0.0,
                "total": total,
                "partial_close_note": "Partial closes require proportional allocation of prepaid exit commission",
            }
        entry = self.commission_for_volume(lots=entry_lots, sides=1)
        exit_c = self.commission_for_volume(lots=exit_lots, sides=1)
        if entry is None or exit_c is None:
            return {"status": "UNKNOWN", "total": None, "entry": None, "exit": None}
        return {
            "status": "VERIFIED",
            "accounting": "per_side_at_each_leg",
            "entry": entry,
            "exit": exit_c,
            "total": entry + exit_c,
        }

    def partial_close_allocation(
        self, *, total_round_turn_commission: float, closed_lots: float, original_lots: float
    ) -> float | None:
        if self.status != "VERIFIED":
            return None
        if original_lots <= 0:
            return None
        return float(total_round_turn_commission) * (float(closed_lots) / float(original_lots))

    def multiple_fills_commission(self, *, fill_lots: list[float], sides_per_fill: int = 2) -> float | None:
        if self.status != "VERIFIED":
            return None
        total = 0.0
        for lots in fill_lots:
            c = self.commission_for_volume(lots=lots, sides=sides_per_fill)
            if c is None:
                return None
            total += c
        return total

    def commission_adjusted_net_r(self, *, gross_r: float, risk_amount: float, **kwargs: Any) -> float | None:
        if self.status != "VERIFIED":
            return None
        if risk_amount is None or float(risk_amount) == 0:
            return None
        c = self.commission_for_volume(**kwargs)
        if c is None:
            return None
        return float(gross_r) - (float(c) / float(risk_amount))


def calibrate_commission(identity: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    account_type = identity.get("account_type")
    symbol = identity.get("broker_symbol")
    status = "UNKNOWN"
    verified_schedule = None
    published_ref = None

    if account_type in PUBLISHED_XAUUSD_REFERENCE and symbol in ("XAUUSD", "XAUUSDm", "XAUUSDc", "XAUUSDr", "XAUUSDz"):
        # Still require explicit verification flag — identity UNKNOWN blocks activation
        published_ref = {
            "account_type": account_type,
            **PUBLISHED_XAUUSD_REFERENCE[account_type if account_type in PUBLISHED_XAUUSD_REFERENCE else "Raw Spread"],
            "instrument": "XAUUSD",
            "active": False,
            "reason_inactive": "account_type or symbol not account-verified",
        }

    # Never activate published numbers while account_type UNKNOWN
    if account_type == "UNKNOWN" or identity.get("verification_status") != "VERIFIED":
        status = "UNKNOWN"
        verified_schedule = None
    elif account_type in ("Standard", "Standard Cent", "Pro"):
        status = "VERIFIED"
        verified_schedule = {
            "calculation_method": "per_lot_per_side",
            "usd_per_lot_per_side": 0.0,
            "currency": "USD",
            "commission_free": True,
            "charge_round_turn_at_open": False,
            "instrument": "XAUUSD",
            "account_type": account_type,
        }
    elif account_type == "Raw Spread":
        status = "VERIFIED"
        verified_schedule = {
            "calculation_method": "per_lot_per_side",
            "usd_per_lot_per_side": 3.5,
            "currency": "USD",
            "commission_free": False,
            "charge_round_turn_at_open": True,
            "instrument": "XAUUSD",
            "account_type": account_type,
            "source_note": "Activated only after account verification",
        }
    elif account_type == "Zero":
        status = "VERIFIED"
        verified_schedule = {
            "calculation_method": "per_lot_per_side",
            "usd_per_lot_per_side": 5.5,
            "currency": "USD",
            "commission_free": False,
            "charge_round_turn_at_open": True,
            "instrument": "XAUUSD",
            "account_type": account_type,
        }

    out = {
        "commission_status": status,
        "account_type": account_type,
        "broker_symbol": symbol,
        "verified_schedule": verified_schedule,
        "published_investigation_reference_xauusd": {
            k: v for k, v in PUBLISHED_XAUUSD_REFERENCE.items()
        },
        "published_reference_active_in_model": False,
        "distinctions": {
            "spread_cost": "Separate from commission",
            "entry_commission": "May be prepaid with exit at open per Exness docs",
            "exit_commission": "See charge_round_turn_at_open",
            "swap": "Separate overnight financing — not commission",
            "slippage": "Separate fill vs benchmark — not commission",
        },
        "refuses_adjusted_performance_when_unknown": True,
        "registry_sha256": registry.get("sha256"),
        "identity_sha256": identity.get("sha256"),
        "hardcoded_into_active_model": False,
        "reason": (
            "Account type/symbol/currency not account-verified; published XAUUSD figures retained as "
            "investigation reference only"
            if status == "UNKNOWN"
            else "Verified schedule active for mapped account type"
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
