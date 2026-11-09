"""Synthetic provider-style fixtures only. Not real Telegram content."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def vasilytrader_style_fixtures() -> list[dict[str, Any]]:
    """VasilyTrader-style: direction, exact entry, SL, single TP (+ cancel/incomplete)."""
    return [
        {
            "fixture_id": "VT-BUY-001",
            "format_style": "vasilytrader_style",
            "provider_label": "synthetic_vasily_style",
            "msg_id": "vt-syn-1",
            "published_at": "2026-02-01T10:00:00Z",
            "symbol": "XAUUSD",
            "side": "BUY",
            "entry": 2650.50,
            "sl": 2640.00,
            "tp": 2665.00,
            "event": "open",
        },
        {
            "fixture_id": "VT-SELL-001",
            "format_style": "vasilytrader_style",
            "provider_label": "synthetic_vasily_style",
            "msg_id": "vt-syn-2",
            "published_at": "2026-02-01T11:00:00Z",
            "symbol": "XAUUSD",
            "side": "SELL",
            "entry": 2668.00,
            "sl": 2678.00,
            "tp": 2650.00,
            "event": "open",
        },
        {
            "fixture_id": "VT-BUY-SLMOD-001",
            "format_style": "vasilytrader_style",
            "provider_label": "synthetic_vasily_style",
            "msg_id": "vt-syn-3",
            "published_at": "2026-02-01T12:00:00Z",
            "updated_at": "2026-02-01T13:00:00Z",
            "symbol": "XAUUSD",
            "side": "BUY",
            "entry": 2648.00,
            "sl": 2642.00,
            "prior_sl": 2638.00,
            "tp": 2660.00,
            "event": "sl_modified",
            "parent_fixture_id": "VT-BUY-SLMOD-001-OPEN",
        },
        {
            "fixture_id": "VT-CANCEL-001",
            "format_style": "vasilytrader_style",
            "provider_label": "synthetic_vasily_style",
            "msg_id": "vt-syn-4",
            "published_at": "2026-02-01T14:00:00Z",
            "updated_at": "2026-02-01T14:10:00Z",
            "symbol": "XAUUSD",
            "side": "SELL",
            "entry": 2670.00,
            "sl": 2680.00,
            "tp": 2655.00,
            "event": "cancelled",
            "parent_fixture_id": "VT-CANCEL-001-OPEN",
        },
        {
            "fixture_id": "VT-INCOMPLETE-001",
            "format_style": "vasilytrader_style",
            "provider_label": "synthetic_vasily_style",
            "msg_id": "vt-syn-5",
            "published_at": "2026-02-01T15:00:00Z",
            "symbol": "XAUUSD",
            "side": "BUY",
            "entry": 2655.00,
            "sl": None,
            "tp": None,
            "event": "open",
        },
    ]


def anabelsignals_style_fixtures() -> list[dict[str, Any]]:
    """AnabelSignals-style: direction, entry, multiple TPs, SL, and updates."""
    return [
        {
            "fixture_id": "AN-BUY-MTP-001",
            "format_style": "anabelsignals_style",
            "provider_label": "synthetic_anabel_style",
            "msg_id": "an-syn-1",
            "published_at": "2026-02-02T09:00:00Z",
            "instrument": "XAUUSD",
            "direction": "BUY",
            "entry": 2645.00,
            "sl": 2635.00,
            "tps": [2650.00, 2655.00, 2660.00],
            "updates": [],
        },
        {
            "fixture_id": "AN-SELL-MTP-001",
            "format_style": "anabelsignals_style",
            "provider_label": "synthetic_anabel_style",
            "msg_id": "an-syn-2",
            "published_at": "2026-02-02T10:00:00Z",
            "instrument": "XAUUSD",
            "direction": "SELL",
            "entry": 2672.00,
            "sl": 2682.00,
            "tps": [2665.00, 2658.00, 2650.00],
            "updates": [],
        },
        {
            "fixture_id": "AN-BUY-SLMOD-001",
            "format_style": "anabelsignals_style",
            "provider_label": "synthetic_anabel_style",
            "msg_id": "an-syn-3",
            "published_at": "2026-02-02T11:00:00Z",
            "instrument": "XAUUSD",
            "direction": "BUY",
            "entry": 2650.00,
            "sl": 2640.00,
            "tps": [2658.00, 2665.00],
            "updates": [
                {
                    "update_id": "an-syn-3u1",
                    "at": "2026-02-02T12:30:00Z",
                    "kind": "sl_modified",
                    "new_sl": 2645.00,
                }
            ],
        },
        {
            "fixture_id": "AN-CANCEL-001",
            "format_style": "anabelsignals_style",
            "provider_label": "synthetic_anabel_style",
            "msg_id": "an-syn-4",
            "published_at": "2026-02-02T13:00:00Z",
            "instrument": "XAUUSD",
            "direction": "SELL",
            "entry": 2660.00,
            "sl": 2670.00,
            "tps": [2650.00, 2640.00],
            "updates": [
                {
                    "update_id": "an-syn-4u1",
                    "at": "2026-02-02T13:20:00Z",
                    "kind": "cancelled",
                }
            ],
        },
        {
            "fixture_id": "AN-INCOMPLETE-001",
            "format_style": "anabelsignals_style",
            "provider_label": "synthetic_anabel_style",
            "msg_id": "an-syn-5",
            "published_at": "2026-02-02T14:00:00Z",
            "instrument": "XAUUSD",
            "direction": "BUY",
            "entry": None,
            "sl": 2630.00,
            "tps": [],
            "updates": [],
        },
        {
            "fixture_id": "AN-ZONE-AMBIG-001",
            "format_style": "anabelsignals_style",
            "provider_label": "synthetic_anabel_style",
            "msg_id": "an-syn-6",
            "published_at": "2026-02-02T15:00:00Z",
            "instrument": "XAUUSD",
            "direction": "BUY",
            "entry": {"min": 2648.0, "max": 2652.0},
            "sl": 2640.00,
            "tps": [2660.00],
            "updates": [],
        },
    ]


def all_raw_fixtures() -> list[dict[str, Any]]:
    return vasilytrader_style_fixtures() + anabelsignals_style_fixtures()


def fixture_catalog() -> dict[str, Any]:
    vt = vasilytrader_style_fixtures()
    an = anabelsignals_style_fixtures()
    return {
        "real_provider_content": False,
        "telegram_accessed": False,
        "vasilytrader_style_count": len(vt),
        "anabelsignals_style_count": len(an),
        "total_raw_fixtures": len(vt) + len(an),
        "case_coverage": [
            "BUY",
            "SELL",
            "multiple_TP",
            "modified_SL",
            "cancellation",
            "incomplete",
        ],
        "fixtures": deepcopy(all_raw_fixtures()),
    }
