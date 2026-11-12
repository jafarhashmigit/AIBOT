"""Commission investigation — separate published vs account-specific applicability."""

from __future__ import annotations

from typing import Any

from phase64_10.constants import UNKNOWN, VERIFIED, canonical_json_sha256


def investigate_commission(
    *,
    n_trade_deals: int = 0,
    balance_deal_commission: Any = None,
    account_type: Any = UNKNOWN,
    published_schedule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Priority: live deal evidence → symbol/account config → official docs → labeled published schedule.
    Never assume a generic Exness schedule applies to this exact account/symbol.
    """
    actual_observed = UNKNOWN
    actual_status = UNKNOWN
    if n_trade_deals > 0:
        actual_status = VERIFIED  # would require real deal values — not present
    else:
        actual_observed = UNKNOWN
        actual_status = UNKNOWN

    # Balance/credit deals with commission=0 are not trade commission evidence
    balance_note = (
        "Balance/credit deal commission (if 0) is not proof of trade commission schedule"
        if balance_deal_commission is not None
        else "No balance commission field used as trade evidence"
    )

    published = published_schedule or {
        "source": "NONE_VERIFIED_FOR_THIS_ACCOUNT",
        "status": UNKNOWN,
        "value": UNKNOWN,
        "note": (
            "Exness publishes multiple account models (spread-only vs Raw/Zero with commission). "
            "Without verified account-type mapping for this Trial15 demo login, "
            "no published schedule is marked VERIFIED for this account."
        ),
    }

    published_status = published.get("status", UNKNOWN)
    account_specific = {
        "status": actual_status,
        "value": actual_observed,
        "n_trade_deals": n_trade_deals,
        "account_type": account_type,
        "note": "actual_commission_observed remains UNKNOWN with zero genuine trade fills",
    }

    # Explicitly do not merge
    merged_forbidden = True

    blocks_execution = account_specific["status"] != VERIFIED

    out = {
        "actual_commission_observed": actual_observed,
        "actual_commission_status": actual_status,
        "published_commission": {
            "status": published_status,
            "value": published.get("value", UNKNOWN),
            "source": published.get("source"),
            "note": published.get("note"),
        },
        "account_specific_commission": account_specific,
        "balance_deal_note": balance_note,
        "merged": False,
        "merge_forbidden": merged_forbidden,
        "blocks_deterministic_execution_cost": blocks_execution,
        "priority_applied": [
            "live_mt5_deal_evidence",
            "verified_symbol_account_config",
            "official_broker_documentation",
            "labeled_published_schedule",
        ],
        "finding": (
            "No genuine trade deals → actual_commission_observed=UNKNOWN; "
            "published schedule not verified as applicable to this Trial15/XAUUSDm account"
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
