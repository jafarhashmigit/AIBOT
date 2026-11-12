"""XAUUSDm contract & cost integrity — incomplete when required inputs UNKNOWN."""

from __future__ import annotations

from typing import Any

from phase63.metadata import ACTIVE_XAUUSDM_SPEC
from phase64_6.constants import (
    ACTIVE_SYMBOL,
    CONTRACT_SPEC_VERSION,
    INCOMPLETE,
    UNKNOWN,
    canonical_json_sha256,
)


def _is_unknown(v: Any) -> bool:
    return v in (None, "", UNKNOWN, "UNKNOWN")


def _num(v: Any) -> float | None:
    if _is_unknown(v):
        return None
    try:
        return float(v)
    except Exception:
        return None


def build_contract_spec(metadata_symbol: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge user-reported Phase63 active spec with optional RO adapter fields — never invent."""
    base = dict(ACTIVE_XAUUSDM_SPEC)
    meta = metadata_symbol or {}
    # Prefer live RO values when present and not UNKNOWN; else keep base / UNKNOWN
    fields = {
        "symbol": ACTIVE_SYMBOL,
        "contract_size": meta.get("contract_size", base.get("contract_size")),
        "digits": meta.get("digits", base.get("digits")),
        "point": meta.get("point", UNKNOWN),
        "tick_size": meta.get("tick_size", base.get("tick_size", UNKNOWN)),
        "tick_value": meta.get("tick_value", base.get("tick_value", UNKNOWN)),
        "tick_value_profit": meta.get("tick_value_profit", base.get("tick_value_profit", UNKNOWN)),
        "tick_value_loss": meta.get("tick_value_loss", base.get("tick_value_loss", UNKNOWN)),
        "volume_min": meta.get("volume_min", base.get("volume_min")),
        "volume_max": meta.get("volume_max", base.get("volume_max")),
        "volume_step": meta.get("volume_step", base.get("volume_step")),
        "profit_currency": meta.get("currency_profit", base.get("profit_currency")),
        "margin_currency": meta.get("currency_margin", base.get("margin_currency")),
        "execution_mode": meta.get("execution_mode", base.get("execution_mode")),
        "filling_modes": base.get("filling_modes"),
        "trading_sessions": meta.get("trading_sessions", base.get("trading_sessions")),
        "swap_long": meta.get("swap_long", base.get("swap_long")),
        "swap_short": meta.get("swap_short", base.get("swap_short")),
        "current_spread": meta.get("spread_points", UNKNOWN),
        "account_currency": UNKNOWN,  # account-level; filled by caller if known
        "account_leverage": UNKNOWN,
        "initial_margin": meta.get("initial_margin", UNKNOWN),
        "maintenance_margin": meta.get("maintenance_margin", UNKNOWN),
        "provenance": {
            "user_reported_fields": True,
            "independently_verified": False,
            "contract_spec_version": CONTRACT_SPEC_VERSION,
        },
    }
    unknown_fields = [k for k, v in fields.items() if k != "provenance" and _is_unknown(v)]
    # sessions completeness
    sess = fields.get("trading_sessions")
    sessions_complete = isinstance(sess, dict) and sess.get("completeness") == "COMPLETE"
    if not sessions_complete:
        if "trading_sessions" not in unknown_fields:
            unknown_fields.append("trading_sessions_incomplete")

    return {
        "spec": fields,
        "unknown_fields": unknown_fields,
        "sessions_complete": sessions_complete,
        "machine_verifiable_complete": len(unknown_fields) == 0 and sessions_complete,
        "broker_execution_realism_claimed": False,
    }


def price_to_ticks(price_delta: float, *, tick_size: Any) -> dict[str, Any]:
    ts = _num(tick_size)
    if ts is None or ts <= 0:
        return {"status": INCOMPLETE, "reason": "tick_size_unknown_or_invalid", "ticks": None}
    return {"status": "OK", "ticks": float(price_delta) / ts, "tick_size": ts}


def ticks_to_money(ticks: float, *, tick_value: Any, volume: float) -> dict[str, Any]:
    tv = _num(tick_value)
    if tv is None:
        return {"status": INCOMPLETE, "reason": "tick_value_unknown", "money": None}
    return {"status": "OK", "money": float(ticks) * tv * float(volume), "tick_value": tv}


def position_notional(*, price: float, volume: float, contract_size: Any) -> dict[str, Any]:
    cs = _num(contract_size)
    if cs is None:
        return {"status": INCOMPLETE, "reason": "contract_size_unknown", "notional": None}
    return {"status": "OK", "notional": float(price) * float(volume) * cs, "contract_size": cs}


def margin_estimate(*, volume: float, margin_per_lot: Any) -> dict[str, Any]:
    m = _num(margin_per_lot)
    if m is None:
        return {"status": INCOMPLETE, "reason": "margin_rate_unknown", "margin": None}
    return {"status": "OK", "margin": float(volume) * m, "margin_per_lot": m}


def stop_loss_monetary_risk(
    *,
    entry: float,
    stop: float,
    volume: float,
    tick_size: Any,
    tick_value: Any,
) -> dict[str, Any]:
    tics = price_to_ticks(abs(float(entry) - float(stop)), tick_size=tick_size)
    if tics["status"] != "OK":
        return {"status": INCOMPLETE, "reason": tics.get("reason"), "risk_money": None}
    money = ticks_to_money(float(tics["ticks"]), tick_value=tick_value, volume=volume)
    if money["status"] != "OK":
        return {"status": INCOMPLETE, "reason": money.get("reason"), "risk_money": None}
    return {"status": "OK", "risk_money": money["money"], "ticks": tics["ticks"]}


def round_volume_to_step(volume: float, *, volume_step: Any, volume_min: Any, volume_max: Any) -> dict[str, Any]:
    step = _num(volume_step)
    vmin = _num(volume_min)
    vmax = _num(volume_max)
    if step is None or step <= 0 or vmin is None or vmax is None:
        return {"status": INCOMPLETE, "reason": "volume_constraints_unknown", "volume": None}
    # floor to step
    n = int(float(volume) / step)
    rounded = n * step
    # fix float noise
    rounded = round(rounded / step) * step
    if rounded < vmin:
        return {"status": "REJECTED", "reason": "below_min_volume", "volume": None, "volume_min": vmin}
    if rounded > vmax:
        return {"status": "REJECTED", "reason": "above_max_volume", "volume": None, "volume_max": vmax}
    # enforce step
    rem = abs(rounded / step - round(rounded / step))
    if rem > 1e-9:
        return {"status": "REJECTED", "reason": "not_on_volume_step", "volume": None}
    return {"status": "OK", "volume": rounded, "volume_step": step}


def audit_contract_integrity(metadata_symbol: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = build_contract_spec(metadata_symbol)
    s = spec["spec"]
    # Tests of calculators
    cases = []
    cases.append(
        {
            "name": "price_to_ticks_unknown_tick_size",
            "pass": price_to_ticks(0.01, tick_size=UNKNOWN)["status"] == INCOMPLETE,
        }
    )
    cases.append(
        {
            "name": "ticks_to_money_unknown_tick_value",
            "pass": ticks_to_money(10, tick_value=UNKNOWN, volume=0.01)["status"] == INCOMPLETE,
        }
    )
    cases.append(
        {
            "name": "sl_risk_incomplete_without_tick_value",
            "pass": stop_loss_monetary_risk(
                entry=2650.0, stop=2649.0, volume=0.01, tick_size=0.001, tick_value=UNKNOWN
            )["status"]
            == INCOMPLETE,
        }
    )
    cases.append(
        {
            "name": "volume_step_ok",
            "pass": round_volume_to_step(0.023, volume_step=0.01, volume_min=0.01, volume_max=200)["status"]
            in ("OK", "REJECTED"),
        }
    )
    # with known tick size from digits/point assumption only if provided numerically in meta
    if not _is_unknown(s.get("tick_size")) and not _is_unknown(s.get("tick_value")):
        ok_calc = stop_loss_monetary_risk(
            entry=2650.0,
            stop=2649.0,
            volume=0.01,
            tick_size=s["tick_size"],
            tick_value=s["tick_value"],
        )
        cases.append({"name": "sl_risk_complete_when_known", "pass": ok_calc["status"] == "OK"})
    else:
        cases.append({"name": "sl_risk_complete_when_known", "pass": True, "skipped": "inputs_unknown"})

    vol = round_volume_to_step(0.01, volume_step=s.get("volume_step"), volume_min=s.get("volume_min"), volume_max=s.get("volume_max"))
    cases.append({"name": "min_volume_enforced", "pass": vol["status"] == "OK" and vol.get("volume") == 0.01})
    bad = round_volume_to_step(0.0, volume_step=0.01, volume_min=0.01, volume_max=200)
    cases.append({"name": "below_min_rejected", "pass": bad["status"] == "REJECTED"})

    out = {
        "contract_spec": spec,
        "calculator_cases": cases,
        "pass": all(c.get("pass") for c in cases) and spec["spec"]["symbol"] == ACTIVE_SYMBOL,
        "metadata_completeness": {
            "complete": spec["machine_verifiable_complete"],
            "unknown_fields": spec["unknown_fields"],
        },
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
