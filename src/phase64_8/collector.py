"""
Read-only broker evidence collector.

Idempotent under repeated polling, restarts, overlapping windows.
Never fabricates deals from paper decisions. Never calls order_send.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from phase64_5.journal import BrokerEvidenceJournal
from phase64_8.constants import (
    ACTIVE_SYMBOL,
    COLLECTOR_VERSION,
    EXPECTED_DEMO_LOGIN,
    EXPECTED_SERVER,
    SIMULATED_LABEL,
    SUPERSEDED_SYMBOL,
    UNKNOWN,
    canonical_json_sha256,
)
from phase64_8.evidence_backend import (
    EvidenceBackend,
    FakeEvidenceBackend,
    LiveEvidenceBackend,
    _g,
    _utc,
    default_history_window,
)
from phase64_8.normalize import (
    normalize_account,
    normalize_deal,
    normalize_order,
    normalize_position,
    strip_for_journal,
)


class CollectionBlocked(RuntimeError):
    pass


def collect_once(
    backend: EvidenceBackend,
    journal: BrokerEvidenceJournal,
    *,
    symbol: str = ACTIVE_SYMBOL,
    expected_login: int | None = EXPECTED_DEMO_LOGIN,
    expected_server: str | None = EXPECTED_SERVER,
    lookback_days: int = 30,
    synthetic: bool = False,
    evidence_label: str | None = None,
) -> dict[str, Any]:
    retrieved_at = _utc()
    provenance = {
        "source": "MT5_RO_COLLECTOR",
        "collector_version": COLLECTOR_VERSION,
        "synthetic": synthetic,
        "evidence_label": evidence_label or ("LIVE_MT5_API" if not synthetic else SIMULATED_LABEL),
        "retrieved_at_utc": retrieved_at,
        "store": "BROKER_EVIDENCE",
    }

    if symbol == SUPERSEDED_SYMBOL:
        return _blocked("superseded_symbol_requested", retrieved_at)

    if not backend.initialize():
        return _blocked("initialize_failed", retrieved_at, detail=str(backend.last_error()))

    ingest_stats = {
        "INGESTED": 0,
        "DUPLICATE_SUPPRESSED": 0,
        "QUARANTINED": 0,
    }
    records: list[dict[str, Any]] = []
    try:
        term = backend.terminal_info()
        if not bool(_g(term, "connected", False)):
            return _blocked("terminal_disconnected", retrieved_at, last_error=str(backend.last_error()))

        acct = backend.account_info()
        if acct is None:
            return _blocked("account_info_missing", retrieved_at)

        acct_rec = normalize_account(acct, retrieved_at=retrieved_at, provenance=provenance)
        raw_login = acct_rec.pop("_raw_login", None)
        if expected_login is not None and str(raw_login) != str(expected_login):
            return _blocked("unexpected_account", retrieved_at, observed_login_last4=str(raw_login)[-4:] if raw_login else UNKNOWN)
        if expected_server is not None and acct_rec.get("server") != expected_server:
            return _blocked("unexpected_server", retrieved_at, observed_server=acct_rec.get("server"))

        batch_id = journal.begin_batch(
            source_file=f"mt5_ro_collect:{retrieved_at}",
            source_sha256=canonical_json_sha256({"t": retrieved_at, "v": COLLECTOR_VERSION}),
            parser_version=COLLECTOR_VERSION,
        )

        def _ingest(rec: dict[str, Any]) -> None:
            clean = strip_for_journal(rec)
            records.append(clean)
            result = journal.append_event(clean, import_batch_id=batch_id)
            status = result.get("status")
            if status in ingest_stats:
                ingest_stats[status] += 1
            else:
                ingest_stats[status or "OTHER"] = ingest_stats.get(status or "OTHER", 0) + 1

        _ingest(acct_rec)

        positions = backend.positions_get(symbol=symbol)
        if positions is None:
            # Distinguish timeout/disconnect vs empty
            err = backend.last_error()
            if not bool(_g(term, "connected", True)):
                return _blocked("disconnect_during_positions", retrieved_at, last_error=str(err))
            # Treat None with success-ish as empty; timeout backends return None with timeout error
            if err and str(err).lower().find("timeout") >= 0:
                return _blocked("api_timeout_positions", retrieved_at, last_error=str(err))
            positions = ()
        for p in positions:
            prec = normalize_position(p, retrieved_at=retrieved_at, provenance=provenance)
            if prec.get("symbol") not in (symbol, UNKNOWN) and prec.get("symbol"):
                # Unexpected symbol — still capture as evidence, flag in result
                prec = {**prec, "unexpected_symbol": True}
            _ingest(prec)

        orders = backend.orders_get(symbol=symbol)
        if orders is None:
            err = backend.last_error()
            if err and "timeout" in str(err).lower():
                return _blocked("api_timeout_orders", retrieved_at, last_error=str(err))
            orders = ()
        for o in orders:
            _ingest(normalize_order(o, retrieved_at=retrieved_at, provenance=provenance, historical=False))

        date_from, date_to = default_history_window(lookback_days=lookback_days)
        deals = backend.history_deals_get(date_from, date_to)
        if deals is None:
            err = backend.last_error()
            if err and "timeout" in str(err).lower():
                return _blocked("api_timeout_deals", retrieved_at, last_error=str(err))
            deals = ()
        for d in deals:
            _ingest(normalize_deal(d, retrieved_at=retrieved_at, provenance=provenance))

        hist_orders = backend.history_orders_get(date_from, date_to)
        if hist_orders is None:
            err = backend.last_error()
            if err and "timeout" in str(err).lower():
                return _blocked("api_timeout_hist_orders", retrieved_at, last_error=str(err))
            hist_orders = ()
        for o in hist_orders:
            _ingest(normalize_order(o, retrieved_at=retrieved_at, provenance=provenance, historical=True))

        n_trade_deals = sum(1 for r in records if r.get("record_kind") == "BROKER_DEAL")
        n_balance = sum(1 for r in records if r.get("record_kind") == "BROKER_BALANCE_OPERATION")
        n_positions = sum(1 for r in records if r.get("record_kind") == "BROKER_POSITION")
        n_orders = sum(1 for r in records if r.get("record_kind") == "BROKER_ORDER" and not r.get("historical"))

        out = {
            "status": "COLLECTED",
            "fail_closed": False,
            "retrieved_at_utc": retrieved_at,
            "collector_version": COLLECTOR_VERSION,
            "batch_id": batch_id,
            "account_fingerprint": acct_rec.get("account_fingerprint"),
            "server": acct_rec.get("server"),
            "currency": acct_rec.get("currency"),
            "n_records_this_cycle": len(records),
            "n_positions": n_positions,
            "n_open_orders": n_orders,
            "n_trade_deals": n_trade_deals,
            "n_balance_operations": n_balance,
            "n_hist_orders": sum(1 for r in records if r.get("record_kind") == "BROKER_ORDER" and r.get("historical")),
            "ingest_stats": ingest_stats,
            "history_window": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "symbol_filter": symbol,
            "order_send_invoked": False,
            "execution_authorized": False,
            "provenance": provenance,
            "journal_integrity": journal.integrity_report(),
        }
        out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
        return out
    finally:
        backend.shutdown()


def collect_live(
    journal_root: Path,
    *,
    lookback_days: int = 30,
) -> dict[str, Any]:
    journal = BrokerEvidenceJournal(journal_root, allow_synthetic=False, store_label="GENUINE")
    backend = LiveEvidenceBackend()
    return collect_once(
        backend,
        journal,
        synthetic=False,
        evidence_label="LIVE_MT5_API",
        lookback_days=lookback_days,
    )


def collect_fake(
    journal_root: Path,
    backend: FakeEvidenceBackend,
    *,
    allow_synthetic: bool = True,
) -> dict[str, Any]:
    journal = BrokerEvidenceJournal(
        journal_root, allow_synthetic=allow_synthetic, store_label="FIXTURE" if allow_synthetic else "GENUINE"
    )
    return collect_once(
        backend,
        journal,
        synthetic=True,
        evidence_label=SIMULATED_LABEL,
    )


def _blocked(reason: str, retrieved_at: str, **extra: Any) -> dict[str, Any]:
    out = {
        "status": "BLOCKED",
        "fail_closed": True,
        "block_reason": reason,
        "retrieved_at_utc": retrieved_at,
        "order_send_invoked": False,
        "execution_authorized": False,
        "collector_version": COLLECTOR_VERSION,
        **extra,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
