"""Map synthetic provider-style payloads onto phase15a_signal_schema_v1."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from phase15a.schema import empty_signal_template, validate_signal_record
from phase15b.fixtures import (
    anabelsignals_style_fixtures,
    vasilytrader_style_fixtures,
)

SYNTHETIC_PERMISSION = {
    "permission_id": "PHASE15B-SYNTHETIC-AUDIT-ONLY",
    "granted_by": None,
    "granted_at_utc": None,
    "covers_ai_ml": False,
}


def _base_mapped(
    *,
    provider_id: str,
    signal_id: str,
    handle: str,
    message_id: str,
    published_at: str,
    last_updated: str,
) -> dict[str, Any]:
    rec = empty_signal_template()
    rec.update(
        {
            "provider_id": provider_id,
            "signal_id": signal_id,
            "original_message_reference": {
                "channel_handle": handle,
                "message_id": message_id,
                "export_row_id": signal_id,
            },
            "published_at_utc": published_at,
            "last_updated_at_utc": last_updated,
            "instrument": "XAUUSD",
            "permission_reference": deepcopy(SYNTHETIC_PERMISSION),
            "data_provenance": "SYNTHETIC_FIXTURE",
        }
    )
    return rec


def map_vasilytrader_style(raw: dict[str, Any]) -> dict[str, Any]:
    """Exact entry + single TP style → schema v1."""
    published = raw["published_at"]
    updated = raw.get("updated_at") or published
    event = raw.get("event", "open")
    entry = raw.get("entry")
    tp = raw.get("tp")
    sl = raw.get("sl")

    rec = _base_mapped(
        provider_id="synthetic_vasily_style",
        signal_id=raw["fixture_id"],
        handle="@synthetic_vasily_style",
        message_id=str(raw.get("msg_id")),
        published_at=published,
        last_updated=updated,
    )

    side = raw.get("side")
    rec["direction"] = side if side in ("BUY", "SELL") else "UNKNOWN"

    if entry is None:
        rec["entry_type"] = "UNKNOWN"
        rec["entry_min"] = None
        rec["entry_max"] = None
    else:
        rec["entry_type"] = "MARKET"
        rec["entry_min"] = float(entry)
        rec["entry_max"] = float(entry)

    rec["stop_loss"] = float(sl) if sl is not None else None
    rec["take_profit_levels"] = [float(tp)] if tp is not None else []

    if event == "cancelled":
        rec["status"] = "CANCELLED"
        rec["update_reference"] = {
            "parent_signal_id": raw.get("parent_fixture_id"),
            "update_kind": "CANCELLED",
            "prior_stop_loss": float(sl) if sl is not None else None,
            "prior_take_profit_levels": [float(tp)] if tp is not None else None,
        }
    elif event == "sl_modified":
        rec["status"] = "MODIFIED"
        prior = raw.get("prior_sl")
        rec["update_reference"] = {
            "parent_signal_id": raw.get("parent_fixture_id") or raw["fixture_id"],
            "update_kind": "STOP_LOSS_MODIFIED",
            "prior_stop_loss": float(prior) if prior is not None else None,
            "prior_take_profit_levels": [float(tp)] if tp is not None else None,
        }
    else:
        rec["status"] = "OPEN"
        rec["update_reference"] = {
            "parent_signal_id": None,
            "update_kind": None,
            "prior_stop_loss": None,
            "prior_take_profit_levels": None,
        }

    missing_core = entry is None or sl is None or tp is None or side not in ("BUY", "SELL")
    if missing_core:
        rec["status"] = "INCOMPLETE" if event == "open" else rec["status"]
        rec["completeness_status"] = "INCOMPLETE"
    else:
        rec["completeness_status"] = "COMPLETE"

    return rec


def map_anabelsignals_style(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Entry + multi-TP + updates style → one or more schema v1 records."""
    published = raw["published_at"]
    entry = raw.get("entry")
    sl = raw.get("sl")
    tps = list(raw.get("tps") or [])
    direction = raw.get("direction")
    updates = list(raw.get("updates") or [])

    base = _base_mapped(
        provider_id="synthetic_anabel_style",
        signal_id=raw["fixture_id"],
        handle="@synthetic_anabel_style",
        message_id=str(raw.get("msg_id")),
        published_at=published,
        last_updated=published,
    )
    base["direction"] = direction if direction in ("BUY", "SELL") else "UNKNOWN"

    if isinstance(entry, dict) and "min" in entry and "max" in entry:
        base["entry_type"] = "LIMIT_ZONE"
        base["entry_min"] = float(entry["min"])
        base["entry_max"] = float(entry["max"])
    elif entry is None:
        base["entry_type"] = "UNKNOWN"
        base["entry_min"] = None
        base["entry_max"] = None
    else:
        base["entry_type"] = "MARKET"
        base["entry_min"] = float(entry)
        base["entry_max"] = float(entry)

    base["stop_loss"] = float(sl) if sl is not None else None
    base["take_profit_levels"] = [float(x) for x in tps]
    base["status"] = "OPEN"
    base["update_reference"] = {
        "parent_signal_id": None,
        "update_kind": None,
        "prior_stop_loss": None,
        "prior_take_profit_levels": None,
    }

    incomplete = (
        entry is None
        or sl is None
        or not tps
        or direction not in ("BUY", "SELL")
    )
    if incomplete and not updates:
        base["status"] = "INCOMPLETE"
        base["completeness_status"] = "INCOMPLETE"
    elif isinstance(entry, dict):
        # Zone present is supported; mark complete if SL/TP/direction exist
        base["completeness_status"] = (
            "COMPLETE" if (sl is not None and tps and direction in ("BUY", "SELL")) else "PARTIAL"
        )
    else:
        base["completeness_status"] = "COMPLETE" if not incomplete else "INCOMPLETE"

    records = [base]
    current_sl = base["stop_loss"]
    current_tps = list(base["take_profit_levels"])

    for i, upd in enumerate(updates):
        child = deepcopy(base)
        child["signal_id"] = f"{raw['fixture_id']}-U{i+1}"
        child["original_message_reference"] = {
            "channel_handle": "@synthetic_anabel_style",
            "message_id": str(upd.get("update_id") or f"{raw.get('msg_id')}-u{i+1}"),
            "export_row_id": child["signal_id"],
        }
        child["published_at_utc"] = published  # original publication preserved
        child["last_updated_at_utc"] = upd["at"]
        kind = upd.get("kind")
        if kind == "sl_modified":
            prior_sl = current_sl
            current_sl = float(upd["new_sl"])
            child["stop_loss"] = current_sl
            child["take_profit_levels"] = list(current_tps)
            child["status"] = "MODIFIED"
            child["update_reference"] = {
                "parent_signal_id": raw["fixture_id"],
                "update_kind": "STOP_LOSS_MODIFIED",
                "prior_stop_loss": prior_sl,
                "prior_take_profit_levels": list(current_tps),
            }
            child["completeness_status"] = "COMPLETE"
        elif kind == "cancelled":
            child["stop_loss"] = current_sl
            child["take_profit_levels"] = list(current_tps)
            child["status"] = "CANCELLED"
            child["update_reference"] = {
                "parent_signal_id": raw["fixture_id"],
                "update_kind": "CANCELLED",
                "prior_stop_loss": current_sl,
                "prior_take_profit_levels": list(current_tps),
            }
            child["completeness_status"] = "COMPLETE"
        else:
            child["status"] = "AMBIGUOUS"
            child["completeness_status"] = "AMBIGUOUS"
            child["update_reference"] = {
                "parent_signal_id": raw["fixture_id"],
                "update_kind": kind,
                "prior_stop_loss": current_sl,
                "prior_take_profit_levels": list(current_tps),
            }
        records.append(child)

    return records


def map_all_fixtures() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in vasilytrader_style_fixtures():
        out.append(map_vasilytrader_style(raw))
    for raw in anabelsignals_style_fixtures():
        out.extend(map_anabelsignals_style(raw))
    return out


def validate_mapped(records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    records = records if records is not None else map_all_fixtures()
    results = []
    all_ok = True
    for rec in records:
        errs = validate_signal_record(rec)
        ok = not errs
        if not ok:
            all_ok = False
        results.append({"signal_id": rec.get("signal_id"), "ok": ok, "errors": errs})
    return {"all_ok": all_ok, "count": len(records), "results": results}
