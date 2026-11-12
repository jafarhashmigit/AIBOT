"""Official Exness session-source inventory and provenance."""

from __future__ import annotations

from typing import Any

from phase64_12.constants import (
    ACTIVE_SYMBOL,
    BASE_INSTRUMENT,
    BROKER_PUBLISHED_SESSION,
    RETRIEVAL_DATE,
    SRC_COMMODITIES,
    SRC_DST_UPDATE,
    SRC_MT_TIMEZONE,
    SRC_STANDARD,
    SRC_SUFFIXES,
    SRC_TRADING_HOURS,
    canonical_json_sha256,
)


def official_source_inventory() -> dict[str, Any]:
    sources = [
        {
            "source_id": "exness_instrument_trading_hours",
            "url": SRC_TRADING_HOURS,
            "title": "Instrument trading hours – Exness Help Center",
            "retrieval_date": RETRIEVAL_DATE,
            "page_updated": "2026-11-11",
            "instrument_or_category": "All instruments; notes gold (XAUUSD) closed during forex rollover",
            "account_platform_conditions": "Exness trading servers UTC+0; MT5 synchronized",
            "published_timezone": "UTC+0",
            "session_information": (
                "Interactive schedule tool; DST summer/winter table; rollover 21:00 UTC summer / "
                "22:00 UTC winter; holiday calendar 2026; weekend maintenance windows"
            ),
            "explicitly_covers_xauusdm": False,
            "covers_xauusd": True,
            "generic_vs_suffix": "Generic XAUUSD / gold references; no XAUUSDm string",
            "evidence_kind": BROKER_PUBLISHED_SESSION,
            "third_party": False,
        },
        {
            "source_id": "exness_dst_update_2026_11_01",
            "url": SRC_DST_UPDATE,
            "title": "Trading Hours Update: End of US Daylight Saving Time (01 Nov 2026)",
            "retrieval_date": RETRIEVAL_DATE,
            "page_updated": "2026-11-03",
            "instrument_or_category": "Metals incl. XAUUSD, XAUUSD 247, XAUAUD, XAUEUR, XAUGBP, XAG, …",
            "account_platform_conditions": "Revised schedule in UTC; applies after US DST end 01 Nov 2026",
            "published_timezone": "UTC",
            "session_information": (
                "Exact weekday segments for XAUUSD summer vs winter including Close Only windows"
            ),
            "explicitly_covers_xauusdm": False,
            "covers_xauusd": True,
            "generic_vs_suffix": "Lists XAUUSD and XAUUSD 247 separately; no XAUUSDm string",
            "evidence_kind": BROKER_PUBLISHED_SESSION,
            "third_party": False,
        },
        {
            "source_id": "exness_mt_timezone",
            "url": SRC_MT_TIMEZONE,
            "title": "What is the default timezone set for MetaTrader?",
            "retrieval_date": RETRIEVAL_DATE,
            "page_updated": "2026-08-22",
            "instrument_or_category": "Platform-wide",
            "account_platform_conditions": "MT4/MT5 synchronized to Exness servers",
            "published_timezone": "GMT+0",
            "session_information": "Server time fixed GMT+0; cannot be changed by client",
            "explicitly_covers_xauusdm": False,
            "covers_xauusd": False,
            "generic_vs_suffix": "N/A — timezone only",
            "evidence_kind": BROKER_PUBLISHED_SESSION,
            "third_party": False,
        },
        {
            "source_id": "exness_account_type_suffixes",
            "url": SRC_SUFFIXES,
            "title": "Account type suffixes – Exness Help Center",
            "retrieval_date": RETRIEVAL_DATE,
            "page_updated": "retrieved_2026_11_12",
            "instrument_or_category": f"Standard → {ACTIVE_SYMBOL} example",
            "account_platform_conditions": "Standard MT4/MT5 uses -m suffix",
            "published_timezone": "N/A",
            "session_information": "No hours; establishes XAUUSDm as Standard naming of XAUUSD",
            "explicitly_covers_xauusdm": True,
            "covers_xauusd": True,
            "generic_vs_suffix": f"Explicit example {ACTIVE_SYMBOL} for Standard; Pro uses {BASE_INSTRUMENT}",
            "evidence_kind": BROKER_PUBLISHED_SESSION,
            "third_party": False,
        },
        {
            "source_id": "exness_commodities_xauusd",
            "url": SRC_COMMODITIES,
            "title": "Commodities – Exness Help Center",
            "retrieval_date": RETRIEVAL_DATE,
            "page_updated": "2026-11-09",
            "instrument_or_category": "XAUUSD gold; Standard among account types",
            "account_platform_conditions": "Standard, Cent, Pro, Raw, Zero; MT4/MT5",
            "published_timezone": "N/A",
            "session_information": "Specs (contract 100); not a weekday hour table",
            "explicitly_covers_xauusdm": False,
            "covers_xauusd": True,
            "generic_vs_suffix": "Uses XAUUSD; lists Standard as supported account type",
            "evidence_kind": BROKER_PUBLISHED_SESSION,
            "third_party": False,
        },
        {
            "source_id": "exness_standard_account",
            "url": SRC_STANDARD,
            "title": "Standard account – Exness Help Center",
            "retrieval_date": RETRIEVAL_DATE,
            "page_updated": "2026-09-26",
            "instrument_or_category": "Standard account features",
            "account_platform_conditions": "Suffix -m; GMT+0 lot-size day/night windows",
            "published_timezone": "GMT+0 (lot limits)",
            "session_information": "Not instrument session schedule; confirms Standard -m",
            "explicitly_covers_xauusdm": False,
            "covers_xauusd": False,
            "generic_vs_suffix": "Suffix -m for Standard",
            "evidence_kind": BROKER_PUBLISHED_SESSION,
            "third_party": False,
        },
    ]
    out = {
        "n_sources": len(sources),
        "third_party_used": False,
        "sources": sources,
        "primary_hour_source": "exness_dst_update_2026_11_01",
        "primary_applicability_source": "exness_account_type_suffixes",
        "primary_timezone_source": "exness_mt_timezone",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
