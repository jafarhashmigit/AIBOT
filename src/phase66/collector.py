"""Read-only market evidence collector — symbol_info + copy_rates only."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_5.journal import BrokerEvidenceJournal
from phase64_6.readonly_adapter import FakeMt5Backend, LiveMt5Backend, Mt5Backend
from phase64_13.schedule import state_at_utc
from phase66.constants import (
    ACTIVE_SYMBOL,
    BROKER_OBSERVED,
    COLLECTOR_VERSION,
    EXPECTED_DEMO_LOGIN,
    EXPECTED_SERVER,
    FIXTURE_JOURNAL_ROOT,
    JOURNAL_ROOT,
    SUPERSEDED_SYMBOL,
    SYNTHETIC_TEST_FIXTURE,
    canonical_json_sha256,
)
from phase66.quality import classify_unavailability, validate_m5_bar, validate_quote
from phase66.schema import build_m5_record, build_quote_record, utc_now
from phase66.watermark import advance_watermark, load_watermark, save_watermark


def _g(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _session_for_now() -> str:
    return state_at_utc(datetime.now(timezone.utc))["state"]


def _stamp_provenance(
    rec: dict[str, Any],
    *,
    synthetic: bool,
    kind: str,
    collector_started_utc: str | None,
    collection_time_utc: str,
    cycle: int | None,
) -> dict[str, Any]:
    """Additive provenance — does not alter stable_key / body_hash for idempotency."""
    out = dict(rec)
    if synthetic:
        out["evidence_provenance"] = "SYNTHETIC_FIXTURE"
    elif kind == "quote":
        out["evidence_provenance"] = "BROKER_OBSERVED_QUOTE"
    elif kind == "m5" and collector_started_utc:
        try:
            from datetime import timedelta

            srv = datetime.fromisoformat(str(rec.get("server_timestamp_utc") or "").replace("Z", "+00:00"))
            start = datetime.fromisoformat(collector_started_utc.replace("Z", "+00:00"))
            if srv.tzinfo is None:
                srv = srv.replace(tzinfo=timezone.utc)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            bar_close = srv + timedelta(minutes=5)
            if bar_close <= start:
                out["evidence_provenance"] = "HISTORICAL_BACKFILL"
            else:
                end = datetime.fromisoformat(collection_time_utc.replace("Z", "+00:00"))
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
                out["evidence_provenance"] = (
                    "BROKER_OBSERVED_LIVE_BAR" if bar_close <= end else "LIVE_INCOMPLETE_OR_FORMING_M5"
                )
        except Exception:
            out["evidence_provenance"] = "M5_UNCLASSIFIED"
    else:
        out["evidence_provenance"] = rec.get("source_classification")
    if collector_started_utc:
        out["collector_started_utc"] = collector_started_utc
    if cycle is not None:
        out["collector_cycle"] = cycle
    return out


def collect_once(
    backend: Mt5Backend,
    journal: BrokerEvidenceJournal,
    *,
    symbol: str = ACTIVE_SYMBOL,
    expected_login: int | None = EXPECTED_DEMO_LOGIN,
    expected_server: str | None = EXPECTED_SERVER,
    synthetic: bool = False,
    watermark_path: Path | None = None,
    m5_count: int = 3,
    collector_started_utc: str | None = None,
    collector_cycle: int | None = None,
) -> dict[str, Any]:
    retrieved = utc_now()
    evidence_class = SYNTHETIC_TEST_FIXTURE if synthetic else BROKER_OBSERVED
    started = collector_started_utc or retrieved
    wm = load_watermark(watermark_path)

    if symbol == SUPERSEDED_SYMBOL:
        return {"status": "BLOCKED", "reason": "superseded_symbol", "retrieved_at_utc": retrieved}
    if symbol != ACTIVE_SYMBOL:
        return {"status": "BLOCKED", "reason": "unexpected_symbol", "retrieved_at_utc": retrieved}

    if not backend.initialize():
        return {
            "status": "BLOCKED",
            "reason": "initialize_failed",
            "detail": str(backend.last_error()),
            "retrieved_at_utc": retrieved,
            "unavailability": classify_unavailability(session_state="UNKNOWN", connected=False),
        }

    stats = {
        "INGESTED": 0,
        "DUPLICATE_SUPPRESSED": 0,
        "QUARANTINED": 0,
        "REJECTED": 0,
        "CONFLICTING_EVIDENCE": 0,
        "FORMING_SKIPPED": 0,
        "LIVE_CLOSED_INGESTED": 0,
        "HISTORICAL_BACKFILL_INGESTED": 0,
    }
    records: list[dict[str, Any]] = []
    try:
        term = backend.terminal_info()
        connected = bool(_g(term, "connected", False))
        if not connected:
            return {
                "status": "BLOCKED",
                "reason": "terminal_disconnected",
                "retrieved_at_utc": retrieved,
                "unavailability": classify_unavailability(session_state=_session_for_now(), connected=False),
            }

        acct = backend.account_info()
        login = _g(acct, "login")
        server = _g(acct, "server")
        if expected_login is not None and str(login) != str(expected_login):
            return {"status": "BLOCKED", "reason": "unexpected_account", "retrieved_at_utc": retrieved}
        if expected_server is not None and server != expected_server:
            return {"status": "BLOCKED", "reason": "unexpected_server", "observed_server": server, "retrieved_at_utc": retrieved}

        sym = backend.symbol_info(symbol)
        if sym is None:
            return {"status": "BLOCKED", "reason": "symbol_info_missing", "retrieved_at_utc": retrieved}

        bid = _g(sym, "bid")
        ask = _g(sym, "ask")
        # symbol time if present
        tsec = _g(sym, "time")
        if tsec:
            server_ts = datetime.fromtimestamp(int(tsec), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            server_ts = retrieved

        session_state = state_at_utc(datetime.fromisoformat(server_ts.replace("Z", "+00:00")))["state"]
        qv = validate_quote(
            symbol=symbol,
            bid=float(bid) if bid is not None else None,
            ask=float(ask) if ask is not None else None,
            server_time_utc=server_ts,
            collection_time_utc=retrieved,
            tick_size=float(_g(sym, "trade_tick_size") or _g(sym, "point") or 0.001),
        )

        batch_id = journal.begin_batch(
            source_file=f"phase66_market:{retrieved}",
            source_sha256=canonical_json_sha256({"t": retrieved, "v": COLLECTOR_VERSION}),
            parser_version=COLLECTOR_VERSION,
        )

        quote = build_quote_record(
            bid=float(bid or 0),
            ask=float(ask or 0),
            server_time_utc=server_ts,
            collection_time_utc=retrieved,
            source_server=str(server),
            session_state=session_state,
            evidence_class=evidence_class,
            raw_payload={"bid": bid, "ask": ask, "time": tsec, "name": _g(sym, "name")},
            validation_status=qv["validation_status"],
            rejection_reason=";".join(qv["rejection_reasons"]) or None,
        )
        quote = _stamp_provenance(
            quote,
            synthetic=synthetic,
            kind="quote",
            collector_started_utc=started,
            collection_time_utc=retrieved,
            cycle=collector_cycle,
        )

        if qv["validation_status"] != "OK":
            journal.quarantine(quote, quote["rejection_reason"] or "quote_rejected")
            stats["REJECTED"] += 1
            stats["QUARANTINED"] += 1
        else:
            # out-of-order vs watermark
            last_q = wm.get("last_quote_server_ts")
            if last_q and server_ts < last_q:
                journal.quarantine({**quote, "note": "out_of_order"}, "out_of_order_observation")
                stats["QUARANTINED"] += 1
            else:
                res = journal.append_event(quote, import_batch_id=batch_id)
                st = res.get("status")
                if st == "INGESTED":
                    stats["INGESTED"] += 1
                    records.append(quote)
                    wm = advance_watermark(wm, quote_ts=server_ts, ingested=1)
                elif st == "DUPLICATE_SUPPRESSED":
                    stats["DUPLICATE_SUPPRESSED"] += 1
                    wm = advance_watermark(wm, duplicates=1)
                else:
                    stats["QUARANTINED"] += 1
                    if res.get("reason") == "conflicting_broker_evidence":
                        stats["CONFLICTING_EVIDENCE"] += 1

        # M5 rates (permitted)
        rates_raw = backend.copy_rates_from_pos(symbol, 5, 0, m5_count)
        if rates_raw is None:
            rates = []
        else:
            try:
                rates = list(rates_raw)
            except TypeError:
                rates = []
        last_m5 = None
        for r in rates:
            # normalize rate dict / numpy structured row
            if not isinstance(r, dict):
                names = getattr(getattr(r, "dtype", None), "names", None)
                if names:
                    r = {n: r[n].item() if hasattr(r[n], "item") else r[n] for n in names}
                else:
                    r = {
                        "time": _g(r, "time"),
                        "open": _g(r, "open"),
                        "high": _g(r, "high"),
                        "low": _g(r, "low"),
                        "close": _g(r, "close"),
                        "tick_volume": _g(r, "tick_volume"),
                        "spread": _g(r, "spread"),
                    }
            t = r.get("time")
            if t and "timestamp_utc" not in r:
                r["timestamp_utc"] = datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            # Never journal forming/incomplete bars — OHLC still changing → would conflict under identity keys
            try:
                from datetime import timedelta

                srv_dt = datetime.fromisoformat(str(r["timestamp_utc"]).replace("Z", "+00:00"))
                if srv_dt.tzinfo is None:
                    srv_dt = srv_dt.replace(tzinfo=timezone.utc)
                bar_close = srv_dt + timedelta(minutes=5)
                coll_dt = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
                if coll_dt.tzinfo is None:
                    coll_dt = coll_dt.replace(tzinfo=timezone.utc)
                if bar_close > coll_dt:
                    stats["FORMING_SKIPPED"] += 1
                    continue
            except Exception:
                stats["FORMING_SKIPPED"] += 1
                continue
            mv = validate_m5_bar(r, symbol=symbol)
            m5rec = build_m5_record(
                bar=r,
                collection_time_utc=retrieved,
                source_server=str(server),
                session_state=session_state,
                evidence_class=evidence_class,
                validation_status=mv["validation_status"],
                rejection_reason=";".join(mv["rejection_reasons"]) or None,
            )
            m5rec = _stamp_provenance(
                m5rec,
                synthetic=synthetic,
                kind="m5",
                collector_started_utc=started,
                collection_time_utc=retrieved,
                cycle=collector_cycle,
            )
            if mv["validation_status"] != "OK":
                journal.quarantine(m5rec, m5rec["rejection_reason"] or "m5_rejected")
                stats["REJECTED"] += 1
                stats["QUARANTINED"] += 1
                continue
            res = journal.append_event(m5rec, import_batch_id=batch_id)
            if res.get("status") == "INGESTED":
                stats["INGESTED"] += 1
                records.append(m5rec)
                last_m5 = m5rec["server_timestamp_utc"]
                wm = advance_watermark(wm, m5_ts=last_m5, ingested=1)
                prov = m5rec.get("evidence_provenance")
                if prov == "BROKER_OBSERVED_LIVE_BAR":
                    stats["LIVE_CLOSED_INGESTED"] += 1
                elif prov == "HISTORICAL_BACKFILL":
                    stats["HISTORICAL_BACKFILL_INGESTED"] += 1
            elif res.get("status") == "DUPLICATE_SUPPRESSED":
                stats["DUPLICATE_SUPPRESSED"] += 1
                wm = advance_watermark(wm, duplicates=1)
            else:
                stats["QUARANTINED"] += 1
                if res.get("reason") == "conflicting_broker_evidence":
                    stats["CONFLICTING_EVIDENCE"] += 1

        save_watermark(wm, watermark_path)
        return {
            "status": "OK",
            "retrieved_at_utc": retrieved,
            "session_state": session_state,
            "stats": stats,
            "n_records": len(records),
            "evidence_class": evidence_class,
            "collector_version": COLLECTOR_VERSION,
            "authorizes_execution": False,
            "unavailability": classify_unavailability(session_state=session_state, connected=True),
            "watermark": wm,
            "journal_integrity": journal.integrity_report(),
        }
    finally:
        try:
            backend.shutdown()
        except Exception:
            pass


def collect_fixture_cycle(
    *,
    journal_root: Path | None = None,
    rounds: int = 2,
    wall_clock_gap_sec: float = 0.0,
    frozen_server_unix: int | None = None,
) -> dict[str, Any]:
    """Deterministic fixture collection for engineering verification.

    Market identity is frozen (fixed server timestamps). Optional wall_clock_gap_sec
    between rounds proves content_hash independence from retrieval time.
    Pass frozen_server_unix to keep identity stable across separate process-style calls.
    """
    import time

    root = journal_root or FIXTURE_JOURNAL_ROOT
    wm_path = root / "watermark.json"
    journal = BrokerEvidenceJournal(root, allow_synthetic=True, store_label="FIXTURE")
    backend = FakeMt5Backend()
    # Freeze market identity for all rounds. Use a recent-but-fixed server clock so
    # quality gates do not reject as stale, while wall-clock gaps between rounds
    # still prove retrieval-time independence of content_hash.
    now = int(frozen_server_unix) if frozen_server_unix is not None else (int(datetime.now(timezone.utc).timestamp()) - 10)
    backend.symbol = {
        **(backend.symbol or {}),
        "name": ACTIVE_SYMBOL,
        "bid": 2650.1,
        "ask": 2650.35,
        "time": now,
        "point": 0.001,
        "trade_tick_size": 0.001,
    }
    backend.rates = [
        {
            "time": now - 300,
            "open": 2649.0,
            "high": 2651.0,
            "low": 2648.5,
            "close": 2650.0,
            "tick_volume": 100,
            "spread": 25,
            "timestamp_utc": datetime.fromtimestamp(now - 300, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    ]
    results = []
    for i in range(rounds):
        if i > 0 and wall_clock_gap_sec > 0:
            time.sleep(float(wall_clock_gap_sec))
        results.append(collect_once(backend, journal, synthetic=True, watermark_path=wm_path, m5_count=1))
    return {
        "rounds": results,
        "idempotent_second_round_duplicates": results[-1]["stats"]["DUPLICATE_SUPPRESSED"] > 0 if len(results) > 1 else None,
        "journal_integrity": journal.integrity_report(),
        "n_events": len(journal.all_events()),
        "genuine_broker_observations": False,
        "synthetic_fixture_only": True,
        "wall_clock_gap_sec": wall_clock_gap_sec,
        "frozen_server_time_unix": now,
    }


def try_live_collect(*, journal_root: Path | None = None) -> dict[str, Any]:
    """Optional live attempt — never fabricates success."""
    root = journal_root or JOURNAL_ROOT
    journal = BrokerEvidenceJournal(root, allow_synthetic=False, store_label="GENUINE")
    try:
        backend = LiveMt5Backend()
    except Exception as exc:
        return {"status": "LIVE_UNAVAILABLE", "reason": str(exc), "genuine_observations": 0}
    try:
        out = collect_once(backend, journal, synthetic=False, watermark_path=root / "watermark.json")
    except Exception as exc:
        return {"status": "LIVE_ERROR", "reason": str(exc), "genuine_observations": 0}
    out["genuine_observations"] = out.get("stats", {}).get("INGESTED", 0) if out.get("status") == "OK" else 0
    return out
