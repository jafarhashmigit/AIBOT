"""Official Exness documentation evidence registry — claims with provenance."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase61.constants import OFFICIAL_URLS, canonical_json_sha256


def _fact(
    *,
    claim: str,
    source_url: str,
    source_updated: str | None,
    instrument: str | None,
    account_applicability: str,
    units: str | None,
    verification_status: str,
    account_specific_confirmation_required: bool,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "claim": claim,
        "source_url": source_url,
        "source_publication_or_update_date": source_updated,
        "retrieval_timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "instrument_applicability": instrument,
        "account_applicability": account_applicability,
        "currency_and_units": units,
        "verification_status": verification_status,
        "account_specific_confirmation_required": account_specific_confirmation_required,
        "notes": notes,
    }


def build_official_evidence_registry() -> dict[str, Any]:
    """Facts recorded from official Help Center retrievals during Phase 61.

    These are investigation references — NOT automatic active account configuration.
    """
    facts = [
        _fact(
            claim="Exness account types include Standard Cent, Standard, Pro, Raw Spread, Zero",
            source_url=OFFICIAL_URLS["account_types"],
            source_updated="2026-10-27",
            instrument=None,
            account_applicability="all_listed_types",
            units=None,
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
            notes="Does not identify which type the user holds",
        ),
        _fact(
            claim="Standard Cent / Standard / Pro: commission No (at-a-glance table)",
            source_url=OFFICIAL_URLS["account_types"],
            source_updated="2026-10-27",
            instrument="general",
            account_applicability="Standard Cent, Standard, Pro",
            units="commission=No per table",
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
        ),
        _fact(
            claim="Raw Spread: commission up to 3.50 USD each side per lot (at-a-glance)",
            source_url=OFFICIAL_URLS["account_types"],
            source_updated="2026-10-27",
            instrument="general",
            account_applicability="Raw Spread",
            units="USD each side per lot (up to 3.50)",
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
            notes="Instrument-specific values may differ; see Commodities article for XAUUSD",
        ),
        _fact(
            claim="Zero: commission from 0.05 USD each side per lot (at-a-glance)",
            source_url=OFFICIAL_URLS["account_types"],
            source_updated="2026-10-27",
            instrument="general",
            account_applicability="Zero",
            units="USD each side per lot (from 0.05)",
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
        ),
        _fact(
            claim="Only Zero and Raw Spread have trading commission; Standard, Standard Cent, Pro are commission-free",
            source_url=OFFICIAL_URLS["commission_fee"],
            source_updated="2026-09-29",
            instrument="general",
            account_applicability="all_types",
            units=None,
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
        ),
        _fact(
            claim="When commission applies, it is based on volume in both directions; charged for open and close as the order is opened",
            source_url=OFFICIAL_URLS["commission_fee"],
            source_updated="2026-09-29",
            instrument="commissionable_accounts",
            account_applicability="Raw Spread, Zero",
            units="charged at open for both sides",
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
        ),
        _fact(
            claim="XAUUSD contract size 100 troy ounces; pip size 0.01; min volume 0.01 lot; max 200 lots",
            source_url=OFFICIAL_URLS["commodities"],
            source_updated="2026-11-09",
            instrument="XAUUSD",
            account_applicability="Standard, Standard Cent, Pro, Raw Spread, Zero",
            units="lot / troy ounce / price pip 0.01",
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
        ),
        _fact(
            claim="XAUUSD execution: Market execution; Instant execution for Pro accounts only",
            source_url=OFFICIAL_URLS["commodities"],
            source_updated="2026-11-09",
            instrument="XAUUSD",
            account_applicability="Pro may use Instant; others Market",
            units=None,
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
        ),
        _fact(
            claim="XAUUSD trading commission: 3.5 USD for Raw Spread; 5.5 USD for Zero (per lot, per side)",
            source_url=OFFICIAL_URLS["commodities"],
            source_updated="2026-11-09",
            instrument="XAUUSD",
            account_applicability="Raw Spread; Zero",
            units="USD per lot per side",
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
            notes=(
                "Stated commission values are per lot, per side. "
                "MUST NOT be hardcoded into active execution model until account type and symbol verified."
            ),
        ),
        _fact(
            claim="XAUUSD swap: Triple swap on Wednesday; holidays may change schedule",
            source_url=OFFICIAL_URLS["commodities"],
            source_updated="2026-11-09",
            instrument="XAUUSD",
            account_applicability="listed metals accounts",
            units="swap schedule",
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
        ),
        _fact(
            claim="Standard Cent suffix -c (e.g. XAUUSDc); Standard -m (e.g. XAUUSDm); Zero often -z; Raw may use -r or no suffix",
            source_url=OFFICIAL_URLS["account_suffixes"],
            source_updated=None,
            instrument="symbol naming",
            account_applicability="suffix mapping",
            units=None,
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
            notes="Pro / Raw Spread / Zero can all appear as unsuffixed XAUUSD — ambiguous",
        ),
        _fact(
            claim="Pro accounts: Instant execution example symbols without suffix (EURUSD, XAUUSD)",
            source_url=OFFICIAL_URLS["account_suffixes"],
            source_updated=None,
            instrument="XAUUSD",
            account_applicability="Pro",
            units=None,
            verification_status="OFFICIAL_DOC_RETRIEVED",
            account_specific_confirmation_required=True,
        ),
    ]

    out = {
        "broker": "Exness",
        "primary_source": "Exness Help Center (official)",
        "urls_investigated": OFFICIAL_URLS,
        "n_facts": len(facts),
        "facts": facts,
        "active_account_configuration": False,
        "disclaimer": (
            "Official pages do not establish the user's actual account conditions. "
            "Jurisdiction and Personal Area contract specifications may differ."
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
