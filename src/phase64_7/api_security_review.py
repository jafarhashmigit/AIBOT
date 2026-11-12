"""Additional MT5 API security review — proposal only; Phase12 allowlist UNCHANGED."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase64_7.constants import canonical_json_sha256


def _review(
    api: str,
    *,
    data_returned: str,
    rw: str,
    permissions: str,
    sensitivity: str,
    misuse: str,
    failure: str,
    recon_value: str,
    min_permission: str,
    controls: list[str],
    necessary: bool,
    alternative: str,
) -> dict[str, Any]:
    return {
        "api": api,
        "phase12_status": "PROHIBITED" if api in PROHIBITED_MT5_API else (
            "PERMITTED" if api in PERMITTED_MT5_API else "UNLISTED"
        ),
        "data_returned": data_returned,
        "read_write": rw,
        "required_permissions": permissions,
        "data_sensitivity": sensitivity,
        "potential_misuse": misuse,
        "failure_timeout_behavior": failure,
        "reconciliation_value_for_aibot": recon_value,
        "minimum_necessary_permission": min_permission,
        "required_tests_and_controls": controls,
        "genuinely_necessary": necessary,
        "existing_permitted_alternative": alternative,
        "allowlist_changed_in_phase64_7": False,
    }


def build_api_security_review() -> dict[str, Any]:
    reviews = [
        _review(
            "positions_get",
            data_returned="Open positions: ticket, symbol, volume, price_open, sl/tp, profit, magic, comment",
            rw="READ",
            permissions="Connected terminal + account authorized for trading history visibility",
            sensitivity="MEDIUM — live exposure and P&L",
            misuse="Could feed unauthorized sizing/close logic if paired with Close/order_send later",
            failure="None/empty on disconnect; last_error codes; may omit symbols not selected",
            recon_value="HIGH — verify open exposure after partial fills / crash without CSV",
            min_permission="RO wrapper only; symbol filter XAUUSDm; no Close",
            controls=[
                "AST allowlist add with RO adapter isolation",
                "Demo-login + server fingerprint gate",
                "Append-only journal of snapshots",
                "Never call Close/order_send from same module",
            ],
            necessary=True,
            alternative="Manual CSV / Toolbox export (Phase63/64.5) — insufficient for realtime recon",
        ),
        _review(
            "orders_get",
            data_returned="Open/pending orders: ticket, type, volume, price, state, magic, comment",
            rw="READ",
            permissions="Connected terminal",
            sensitivity="MEDIUM — pending order state",
            misuse="Discovery of tickets could enable targeted cancel if cancel APIs added later",
            failure="Empty list / None when disconnected",
            recon_value="HIGH — crash after submit before local ack (UNKNOWN_REQUIRES_RECONCILIATION)",
            min_permission="RO wrapper; filter by magic/comment intent tags",
            controls=["Same as positions_get", "Idempotent ingest by ticket"],
            necessary=True,
            alternative="Manual History Orders export — too slow for timeout recon",
        ),
        _review(
            "history_deals_get",
            data_returned="Historical deals: ticket, order, position, volume, price, commission, swap, profit, time",
            rw="READ",
            permissions="Connected terminal; history range",
            sensitivity="HIGH — full trade economics and identifiers",
            misuse="Bulk export of account economics; privacy if logs leak",
            failure="Empty range; timeout on large windows",
            recon_value="HIGH — native deal evidence vs CSV; commission/swap actuals",
            min_permission="RO; bounded time window; XAUUSDm filter; no store merge with hist/shadow",
            controls=["Bounded lookback", "Sanitize reports", "Append-only BrokerEvidenceJournal"],
            necessary=True,
            alternative="CSV History→Deals export (Phase64.5) — sufficient offline, not realtime",
        ),
        _review(
            "history_orders_get",
            data_returned="Historical orders: ticket, state, type, volume, times",
            rw="READ",
            permissions="Connected terminal",
            sensitivity="MEDIUM-HIGH",
            misuse="Similar to history_deals_get",
            failure="Empty/timeout",
            recon_value="MEDIUM-HIGH — link orders to deals for rejected/cancelled paths",
            min_permission="RO bounded window",
            controls=["Same as history_deals_get"],
            necessary=True,
            alternative="CSV History→Orders — offline ok",
        ),
    ]

    # Historical Phase64.7 proposal; Phase64.8 applied APPROVED_READ_ONLY for these four APIs.
    applied = all(r["phase12_status"] == "PERMITTED" for r in reviews)
    proposal = {
        "status": "APPLIED_BY_PHASE64_8" if applied else "PROPOSAL_ONLY_NOT_APPLIED",
        "phase12_allowlist_unchanged": not applied,
        "proposed_additions": [
            {
                "api": r["api"],
                "rationale": r["reconciliation_value_for_aibot"],
                "minimum_controls": r["required_tests_and_controls"],
            }
            for r in reviews
            if r["genuinely_necessary"]
        ],
        "explicitly_excluded": ["order_send", "buy", "sell", "Close", "order_check", "symbol_select"],
        "approval_required": "Phase64.8 applied RO approvals; order_send remains excluded",
    }

    out = {
        "reviews": reviews,
        "minimal_allowlist_change_proposal": proposal,
        "currently_permitted_sufficient_for_metadata_probe": True,
        "currently_permitted_sufficient_for_realtime_order_recon": applied,
        "superseded_by_phase64_8": applied,
        "pass": (
            all(r["api"] in {"positions_get", "orders_get", "history_deals_get", "history_orders_get"} for r in reviews)
            and "order_send" in PROHIBITED_MT5_API
            and all(x in PROHIBITED_MT5_API for x in ("buy", "sell", "Close", "order_check", "symbol_select"))
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
