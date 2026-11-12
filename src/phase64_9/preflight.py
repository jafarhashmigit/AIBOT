"""Deterministic ExecutionPreflight — validates before any future broker submission."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from phase64_9.constants import (
    ACTIVE_SYMBOL,
    EXPECTED_CURRENCY,
    EXPECTED_DEMO_LOGIN,
    EXPECTED_SERVER,
    PREFLIGHT_REJECTED,
    PREFLIGHT_VERSION,
    RISK_INCOMPLETE,
    SUPERSEDED_SYMBOL,
    UNKNOWN,
    UNAPPROVED,
    VERIFIED_CONTRACT_SIZE,
    VERIFIED_DIGITS,
    VERIFIED_TICK_SIZE,
    VERIFIED_TICK_VALUE,
    canonical_json_sha256,
    sha256_hex,
)
from phase64_9.risk_calc import estimate_total_downside, monetary_risk_from_sl, round_volume_to_step


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class PreflightContext:
    # Identity
    account_fingerprint: str = ""
    expected_fingerprint: str = ""
    server: str = ""
    expected_server: str = EXPECTED_SERVER
    currency: str = ""
    expected_currency: str = EXPECTED_CURRENCY
    login: Any = None
    expected_login: Any = EXPECTED_DEMO_LOGIN
    symbol: str = ACTIVE_SYMBOL
    symbol_spec_hash: str = ""
    expected_symbol_spec_hash: str = ""

    # Market
    bid: float | None = None
    ask: float | None = None
    tick_age_sec: float | None = None
    max_tick_age_sec: float = 120.0
    max_spread_points: float | None = None
    atr: float | None = None
    max_spread_atr_ratio: float | None = None
    trading_session_known: bool = False
    in_trading_session: bool | None = None

    # Order
    direction: str = ""
    volume: float | None = None
    volume_min: float = 0.01
    volume_max: float = 200.0
    volume_step: float = 0.01
    price: float | None = None
    sl: float | None = None
    tp: float | None = None
    min_sl_distance_points: float | None = None
    filling_mode_bitmask: int | None = None
    requested_filling: int | None = None  # 1=FOK, 2=IOC, 4=RETURN

    # Contract / economics
    tick_size: Any = VERIFIED_TICK_SIZE
    tick_value: Any = VERIFIED_TICK_VALUE
    contract_size: Any = VERIFIED_CONTRACT_SIZE
    digits: Any = VERIFIED_DIGITS
    commission: Any = None
    accept_unknown_commission: bool = False
    critical_unknowns: list[str] = field(default_factory=list)

    # Risk policy (must be approved for pass; currently UNAPPROVED → reject)
    risk_policy_status: str = UNAPPROVED
    per_trade_risk_limit: float | None = None
    aggregate_risk_limit: float | None = None
    current_aggregate_risk: float = 0.0
    daily_loss_limit: float | None = None
    current_daily_loss: float = 0.0
    drawdown_limit: float | None = None
    current_drawdown: float = 0.0
    trade_count_limit: int | None = None
    current_trade_count: int = 0
    consecutive_loss_breaker_active: bool = False

    # Lifecycle
    decision_id: str = ""
    decision_action: str = ""
    decision_expired: bool = False
    decision_already_executed: bool = False
    execution_intent_id: str = ""
    intent_unique: bool = True
    unresolved_prior_execution: bool = False


def symbol_spec_hash(
    *,
    tick_size: Any,
    tick_value: Any,
    contract_size: Any,
    digits: Any,
    volume_min: Any,
    volume_step: Any,
) -> str:
    return sha256_hex(
        f"{tick_size}|{tick_value}|{contract_size}|{digits}|{volume_min}|{volume_step}|{ACTIVE_SYMBOL}"
    )


def run_preflight(ctx: PreflightContext) -> dict[str, Any]:
    reasons: list[str] = []
    checks: dict[str, Any] = {}

    # --- Identity ---
    if not ctx.expected_fingerprint or ctx.account_fingerprint != ctx.expected_fingerprint:
        reasons.append("account_fingerprint_mismatch")
    if ctx.server != ctx.expected_server:
        reasons.append("server_mismatch")
    if ctx.currency != ctx.expected_currency:
        reasons.append("currency_mismatch")
    if str(ctx.login) != str(ctx.expected_login):
        reasons.append("login_mismatch")
    if ctx.symbol == SUPERSEDED_SYMBOL or ctx.symbol != ACTIVE_SYMBOL:
        reasons.append(f"symbol_invalid:{ctx.symbol}")
    if not ctx.expected_symbol_spec_hash or ctx.symbol_spec_hash != ctx.expected_symbol_spec_hash:
        reasons.append("symbol_spec_hash_mismatch")
    checks["identity"] = {"pass": not any(r.startswith(("account", "server", "currency", "login", "symbol")) for r in reasons)}

    # --- Market ---
    if ctx.bid is None or ctx.ask is None or ctx.bid <= 0 or ctx.ask <= 0:
        reasons.append("invalid_bid_ask")
    elif ctx.bid >= ctx.ask:
        reasons.append("crossed_market")
    if ctx.tick_age_sec is None or ctx.tick_age_sec > ctx.max_tick_age_sec:
        reasons.append("stale_tick")
    spread_points = None
    if ctx.bid is not None and ctx.ask is not None and ctx.tick_size not in (None, 0, UNKNOWN):
        try:
            spread_points = (float(ctx.ask) - float(ctx.bid)) / float(ctx.tick_size)
        except Exception:
            spread_points = UNKNOWN
            reasons.append("spread_uncomputable")
    if ctx.max_spread_points is not None and spread_points not in (None, UNKNOWN):
        if float(spread_points) > float(ctx.max_spread_points):
            reasons.append("spread_explosion")
    if ctx.max_spread_atr_ratio is not None and ctx.atr not in (None, 0, UNKNOWN) and spread_points not in (None, UNKNOWN):
        if float(spread_points) * float(ctx.tick_size) / float(ctx.atr) > float(ctx.max_spread_atr_ratio):
            reasons.append("spread_atr_excessive")
    if ctx.trading_session_known:
        if ctx.in_trading_session is not True:
            reasons.append("outside_trading_session")
    else:
        # Session unknown → do not invent; flag but allow only if future policy accepts.
        # Current policy: reject when session required and unknown.
        reasons.append("trading_session_unknown")
    checks["market"] = {"spread_points": spread_points, "tick_age_sec": ctx.tick_age_sec}

    # --- Order ---
    d = (ctx.direction or "").upper()
    if d not in ("BUY", "SELL"):
        reasons.append("invalid_direction")
    if ctx.volume is None:
        reasons.append("volume_missing")
    else:
        vr = round_volume_to_step(ctx.volume, ctx.volume_step, ctx.volume_min, ctx.volume_max)
        if not vr["ok"] or not vr.get("aligned", True) and abs(ctx.volume - vr["rounded"]) > 1e-9:
            # require exact alignment
            if abs((ctx.volume / ctx.volume_step) - round(ctx.volume / ctx.volume_step)) > 1e-9:
                reasons.append("volume_not_aligned_to_step")
            if ctx.volume < ctx.volume_min or ctx.volume > ctx.volume_max:
                reasons.append("volume_out_of_range")
        if not vr["ok"]:
            reasons.append(f"volume_invalid:{vr.get('reason')}")
    if ctx.price is None or ctx.price <= 0:
        reasons.append("price_invalid")
    if ctx.sl is None or ctx.sl <= 0:
        reasons.append("sl_invalid")
    if ctx.tp is None or ctx.tp <= 0:
        reasons.append("tp_invalid")
    if d == "BUY" and ctx.sl is not None and ctx.price is not None and ctx.sl >= ctx.price:
        reasons.append("buy_sl_not_below")
    if d == "SELL" and ctx.sl is not None and ctx.price is not None and ctx.sl <= ctx.price:
        reasons.append("sell_sl_not_above")
    if d == "BUY" and ctx.tp is not None and ctx.price is not None and ctx.tp <= ctx.price:
        reasons.append("buy_tp_not_above")
    if d == "SELL" and ctx.tp is not None and ctx.price is not None and ctx.tp >= ctx.price:
        reasons.append("sell_tp_not_below")
    if ctx.min_sl_distance_points is not None and ctx.sl and ctx.price and ctx.tick_size not in (None, 0, UNKNOWN):
        dist = abs(ctx.price - ctx.sl) / float(ctx.tick_size)
        if dist < float(ctx.min_sl_distance_points):
            reasons.append("sl_distance_too_small")
    if ctx.filling_mode_bitmask is not None and ctx.requested_filling is not None:
        if not (int(ctx.filling_mode_bitmask) & int(ctx.requested_filling)):
            reasons.append("unsupported_filling_mode")
    elif ctx.requested_filling is not None and ctx.filling_mode_bitmask is None:
        reasons.append("filling_mode_unknown")
    checks["order"] = {"direction": d, "volume": ctx.volume}

    # --- Economics / critical unknowns ---
    for name, val in (
        ("tick_size", ctx.tick_size),
        ("tick_value", ctx.tick_value),
        ("contract_size", ctx.contract_size),
    ):
        if val in (None, UNKNOWN, 0):
            reasons.append(f"critical_unknown:{name}")
            ctx.critical_unknowns.append(name)
    for u in ctx.critical_unknowns:
        if f"critical_unknown:{u}" not in reasons:
            reasons.append(f"critical_unknown:{u}")

    # --- Risk ---
    if ctx.risk_policy_status != "APPROVED":
        reasons.append("risk_policy_unapproved")
    if ctx.consecutive_loss_breaker_active:
        reasons.append("consecutive_loss_circuit_breaker")
    if ctx.trade_count_limit is not None and ctx.current_trade_count >= ctx.trade_count_limit:
        reasons.append("trade_count_limit")
    if ctx.daily_loss_limit is not None and ctx.current_daily_loss >= ctx.daily_loss_limit:
        reasons.append("daily_loss_limit")
    if ctx.drawdown_limit is not None and ctx.current_drawdown >= ctx.drawdown_limit:
        reasons.append("drawdown_limit")

    risk_result: dict[str, Any] = {"status": RISK_INCOMPLETE}
    if (
        d in ("BUY", "SELL")
        and ctx.price
        and ctx.sl
        and ctx.volume
        and ctx.tick_size not in (None, UNKNOWN, 0)
        and ctx.tick_value not in (None, UNKNOWN, 0)
    ):
        sl_risk = monetary_risk_from_sl(
            direction=d,
            entry=float(ctx.price),
            sl=float(ctx.sl),
            volume=float(ctx.volume),
            tick_size=float(ctx.tick_size),
            tick_value=float(ctx.tick_value),
            contract_size=float(ctx.contract_size) if ctx.contract_size not in (None, UNKNOWN) else VERIFIED_CONTRACT_SIZE,
        )
        risk_result = estimate_total_downside(
            sl_risk=sl_risk,
            spread_points=spread_points,
            volume=float(ctx.volume),
            commission=ctx.commission,
            accept_unknown_commission=ctx.accept_unknown_commission,
            tick_size=float(ctx.tick_size),
            tick_value=float(ctx.tick_value),
        )
        if risk_result.get("status") == RISK_INCOMPLETE:
            reasons.append("risk_incomplete")
        elif ctx.per_trade_risk_limit is not None:
            if float(risk_result["total_estimated_downside"]) > float(ctx.per_trade_risk_limit):
                reasons.append("per_trade_risk_exceeded")
            if ctx.aggregate_risk_limit is not None:
                agg = ctx.current_aggregate_risk + float(risk_result["total_estimated_downside"])
                if agg > float(ctx.aggregate_risk_limit):
                    reasons.append("aggregate_risk_exceeded")
        else:
            # No approved numeric limit → cannot authorize risk
            reasons.append("per_trade_risk_limit_unconfigured")
    else:
        reasons.append("risk_incomplete")
    checks["risk"] = risk_result

    # --- Lifecycle ---
    if not ctx.decision_id:
        reasons.append("missing_canonical_decision")
    if (ctx.decision_action or "").upper() in ("", "WAIT", "REJECTED", "NO_TRADE", "RISK_BLOCKED"):
        reasons.append(f"decision_not_executable:{ctx.decision_action or 'EMPTY'}")
    if ctx.decision_expired:
        reasons.append("decision_expired")
    if ctx.decision_already_executed:
        reasons.append("decision_already_executed")
    if not ctx.execution_intent_id:
        reasons.append("missing_execution_intent")
    if not ctx.intent_unique:
        reasons.append("duplicate_execution_intent")
    if ctx.unresolved_prior_execution:
        reasons.append("unresolved_prior_execution")
    checks["lifecycle"] = {
        "decision_id": ctx.decision_id,
        "intent_id": ctx.execution_intent_id,
    }

    # Deduplicate reasons preserving order
    seen = set()
    uniq = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)

    passed = len(uniq) == 0
    out = {
        "preflight_version": PREFLIGHT_VERSION,
        "status": "PREFLIGHT_PASSED" if passed else PREFLIGHT_REJECTED,
        "passed": passed,
        "reasons": uniq,
        "checks": checks,
        "evaluated_at_utc": _utc(),
        "never_downgrade_to_execution": True,
        "submission_attempted": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def preflight_spec() -> dict[str, Any]:
    return {
        "version": PREFLIGHT_VERSION,
        "categories": ["identity", "market", "order", "risk", "data_economics", "lifecycle"],
        "fail_closed": True,
        "rejection_status": PREFLIGHT_REJECTED,
        "risk_incomplete_blocks": True,
        "note": "Failed preflight never silently becomes execution",
    }
