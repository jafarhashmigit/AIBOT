"""Exact-symbol applicability: XAUUSD published hours → XAUUSDm Standard."""

from __future__ import annotations

from typing import Any

from phase64_12.constants import (
    ACCOUNT_TYPE,
    ACTIVE_SYMBOL,
    BASE_INSTRUMENT,
    PLATFORM,
    SRC_COMMODITIES,
    SRC_DST_UPDATE,
    SRC_SUFFIXES,
    canonical_json_sha256,
)


def build_applicability_matrix() -> dict[str, Any]:
    rows = [
        {
            "evidence": "DST trading-hours update (XAUUSD weekday segments)",
            "instrument": BASE_INSTRUMENT,
            "account_type": "All (schedule by instrument)",
            "platform": "Exness MT / servers UTC",
            "exact_applicability": f"Published for {BASE_INSTRUMENT}; not literally '{ACTIVE_SYMBOL}'",
            "status": "PUBLISHED_FOR_XAUUSD",
        },
        {
            "evidence": "Account type suffixes (Standard → -m, example XAUUSDm)",
            "instrument": ACTIVE_SYMBOL,
            "account_type": ACCOUNT_TYPE,
            "platform": f"{PLATFORM} MT4/MT5",
            "exact_applicability": (
                f"{ACTIVE_SYMBOL} is the official Standard-account symbol form of {BASE_INSTRUMENT}"
            ),
            "status": "APPLICABLE",
        },
        {
            "evidence": "Commodities XAUUSD (Standard among account types; contract 100)",
            "instrument": BASE_INSTRUMENT,
            "account_type": "Standard included",
            "platform": "MT4/MT5",
            "exact_applicability": "Supports Standard; naming via suffix article → XAUUSDm",
            "status": "SUPPORTING",
        },
        {
            "evidence": "XAUUSD 247 schedule (distinct product)",
            "instrument": "XAUUSD247",
            "account_type": "Standard/Pro/Raw/Zero",
            "platform": "MT4/MT5",
            "exact_applicability": f"NOT applicable to {ACTIVE_SYMBOL} (different instrument/hours)",
            "status": "NOT_APPLICABLE",
        },
        {
            "evidence": "Connected Trial15 live symbol XAUUSDm (contract 100, digits 3)",
            "instrument": ACTIVE_SYMBOL,
            "account_type": "Standard demo",
            "platform": PLATFORM,
            "exact_applicability": "Confirms connected symbol matches Standard -m naming + gold contract",
            "status": "ACCOUNT_CONFIRMED_SYMBOL",
        },
    ]

    justified = True
    reasoning = (
        f"Exness Help Center 'Account type suffixes' explicitly lists Standard suffix '-m' with "
        f"example '{ACTIVE_SYMBOL}'. The DST trading-hours article publishes weekday segments for "
        f"'{BASE_INSTRUMENT}' (and separately '{BASE_INSTRUMENT} 247'). Therefore the XAUUSD "
        f"(non-247) schedule applies to {ACTIVE_SYMBOL} on Standard/{PLATFORM}; it does not apply "
        f"to XAUUSD247. Published pages do not print the string '{ACTIVE_SYMBOL}' inside the hour "
        f"table — applicability is via the official suffix mapping, not silent assumption."
    )

    out = {
        "target_symbol": ACTIVE_SYMBOL,
        "published_hour_instrument": BASE_INSTRUMENT,
        "account_type": ACCOUNT_TYPE,
        "platform": PLATFORM,
        "applicability_justified": justified,
        "status": "APPLICABLE_VIA_OFFICIAL_SUFFIX_MAPPING",
        "not_xauusd247": True,
        "rows": rows,
        "source_urls": {
            "suffixes": SRC_SUFFIXES,
            "dst_hours": SRC_DST_UPDATE,
            "commodities": SRC_COMMODITIES,
        },
        "reasoning": reasoning,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
