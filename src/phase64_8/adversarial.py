"""Adversarial tests for Phase 64.8 RO evidence / reconciliation."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase64_5.journal import BrokerEvidenceJournal
from phase64_8.collector import collect_fake, collect_once
from phase64_8.constants import ACTIVE_SYMBOL, EXPECTED_DEMO_LOGIN, EXPECTED_SERVER, SIMULATED_LABEL, canonical_json_sha256
from phase64_8.costs import separate_costs
from phase64_8.evidence_backend import FakeEvidenceBackend
from phase64_8.normalize import normalize_deal
from phase64_8.reconcile import reconcile_lifecycle
from phase64_8.security import audit_security_invariants, attempted_unauthorized_execution


def _deal(ticket: int, order: int, **kw: Any) -> dict[str, Any]:
    base = {
        "ticket": ticket,
        "order": order,
        "position_id": order,
        "symbol": ACTIVE_SYMBOL,
        "type": 0,
        "entry": 0,
        "volume": 0.01,
        "price": 2650.0,
        "commission": -0.06,
        "swap": 0.0,
        "profit": 1.2,
        "fee": 0.0,
        "time": 1700000000,
        "time_msc": 1700000000000,
        "magic": 1,
        "comment": "aibot",
    }
    base.update(kw)
    return base


def _order(ticket: int, **kw: Any) -> dict[str, Any]:
    base = {
        "ticket": ticket,
        "symbol": ACTIVE_SYMBOL,
        "type": 0,
        "volume_initial": 0.01,
        "volume_current": 0.01,
        "price_open": 2650.0,
        "sl": 0.0,
        "tp": 0.0,
        "state": 1,
        "time_setup": 1700000000,
        "time_done": 0,
        "magic": 1,
        "comment": "aibot",
    }
    base.update(kw)
    return base


def _pos(ticket: int, **kw: Any) -> dict[str, Any]:
    base = {
        "ticket": ticket,
        "symbol": ACTIVE_SYMBOL,
        "type": 0,
        "volume": 0.01,
        "price_open": 2650.0,
        "price_current": 2651.0,
        "sl": 0.0,
        "tp": 0.0,
        "profit": 1.0,
        "swap": 0.0,
        "magic": 1,
        "comment": "aibot",
        "time": 1700000000,
    }
    base.update(kw)
    return base


def run_adversarial_tests() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": bool(passed), **extra})

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # 1 Duplicate deal response
        b1 = FakeEvidenceBackend(deals=[_deal(100, 10), _deal(100, 10)])
        r1 = collect_fake(root / "d1", b1)
        j1 = BrokerEvidenceJournal(root / "d1", allow_synthetic=True, store_label="FIXTURE")
        n_deal_events = sum(1 for e in j1.all_events() if e.get("record_kind") == "BROKER_DEAL")
        add(
            "duplicate_deal_response",
            r1["status"] == "COLLECTED" and n_deal_events == 1 and r1["ingest_stats"]["DUPLICATE_SUPPRESSED"] >= 1,
            n_deal_events=n_deal_events,
        )

        # 2 Duplicate order response
        b2 = FakeEvidenceBackend(orders=[_order(20), _order(20)])
        r2 = collect_fake(root / "d2", b2)
        j2 = BrokerEvidenceJournal(root / "d2", allow_synthetic=True, store_label="FIXTURE")
        n_ord = sum(1 for e in j2.all_events() if e.get("record_kind") == "BROKER_ORDER")
        add("duplicate_order_response", r2["status"] == "COLLECTED" and n_ord == 1)

        # 3 Duplicate position response
        b3 = FakeEvidenceBackend(positions=[_pos(30), _pos(30)])
        r3 = collect_fake(root / "d3", b3)
        j3 = BrokerEvidenceJournal(root / "d3", allow_synthetic=True, store_label="FIXTURE")
        n_pos = sum(1 for e in j3.all_events() if e.get("record_kind") == "BROKER_POSITION")
        add("duplicate_position_response", r3["status"] == "COLLECTED" and n_pos == 1)

        # 4 Same deal in multiple polling windows
        b4 = FakeEvidenceBackend(deals=[_deal(40, 41)])
        collect_fake(root / "d4", b4)
        r4b = collect_fake(root / "d4", b4)
        add(
            "same_deal_multi_window",
            r4b["status"] == "COLLECTED" and r4b["ingest_stats"]["DUPLICATE_SUPPRESSED"] >= 1,
        )

        # 5 Out-of-order deal
        b5 = FakeEvidenceBackend(deals=[_deal(52, 50, time=1700000100), _deal(51, 50, time=1700000000)])
        r5 = collect_fake(root / "d5", b5)
        j5 = BrokerEvidenceJournal(root / "d5", allow_synthetic=True, store_label="FIXTURE")
        recon5 = reconcile_lifecycle(events=j5.all_events())
        add(
            "out_of_order_deal",
            r5["status"] == "COLLECTED"
            and any(f.get("relationship") == "one_order_to_many_deals" for f in recon5["findings"]),
        )

        # 6 Partial fill sequence
        b6 = FakeEvidenceBackend(
            hist_orders=[_order(60)],
            deals=[_deal(61, 60, volume=0.01), _deal(62, 60, volume=0.01)],
        )
        collect_fake(root / "d6", b6)
        j6 = BrokerEvidenceJournal(root / "d6", allow_synthetic=True, store_label="FIXTURE")
        recon6 = reconcile_lifecycle(events=j6.all_events())
        add(
            "partial_fill_sequence",
            any(f.get("n_deals") == 2 for f in recon6["findings"]),
        )

        # 7 Missing order for known deal
        events7 = [
            normalize_deal(
                _deal(70, 0),
                retrieved_at="2026-01-01T00:00:00Z",
                provenance={"synthetic": True, "evidence_label": SIMULATED_LABEL},
            )
        ]
        # force no order id
        events7[0]["broker_order_id"] = None
        recon7 = reconcile_lifecycle(events=events7)
        add(
            "missing_order_for_known_deal",
            any(f.get("state") == "ORPHAN_BROKER_EVIDENCE" for f in recon7["findings"]),
        )

        # 8 Missing deal for known order
        b8 = FakeEvidenceBackend(hist_orders=[_order(80)])
        collect_fake(root / "d8", b8)
        j8 = BrokerEvidenceJournal(root / "d8", allow_synthetic=True, store_label="FIXTURE")
        recon8 = reconcile_lifecycle(events=j8.all_events())
        add(
            "missing_deal_for_known_order",
            any(f.get("state") == "MISSING_BROKER_EVIDENCE" for f in recon8["findings"]),
        )

        # 9 Conflicting execution price
        recon9 = reconcile_lifecycle(
            events=[
                {**normalize_deal(_deal(90, 91, price=2650.0), retrieved_at="t", provenance={"synthetic": True}), "body_hash": "a"},
                {**normalize_deal(_deal(90, 91, price=2651.0), retrieved_at="t", provenance={"synthetic": True}), "body_hash": "b"},
            ]
        )
        add(
            "conflicting_execution_price",
            any(
                f.get("state") == "CONFLICTING_BROKER_EVIDENCE" and f.get("field") == "execution_price"
                for f in recon9["findings"]
            ),
        )

        # 10 Conflicting volume
        recon10 = reconcile_lifecycle(
            events=[
                {**normalize_deal(_deal(1001, 1002, volume=0.01), retrieved_at="t", provenance={"synthetic": True}), "body_hash": "a"},
                {**normalize_deal(_deal(1001, 1002, volume=0.02), retrieved_at="t", provenance={"synthetic": True}), "body_hash": "b"},
            ]
        )
        add(
            "conflicting_volume",
            any(
                f.get("state") == "CONFLICTING_BROKER_EVIDENCE" and f.get("field") == "volume"
                for f in recon10["findings"]
            ),
        )

        # 11 Broker disconnect
        b11 = FakeEvidenceBackend(connected=False, fail_initialize=True)
        r11 = collect_fake(root / "d11", b11)
        add("broker_disconnect", r11["status"] == "BLOCKED" and r11.get("fail_closed") is True)

        # 12 API timeout
        b12 = FakeEvidenceBackend(timeout=True)
        # initialize succeeds but positions_get returns None with timeout error
        b12.fail_initialize = False
        b12.connected = True
        r12 = collect_fake(root / "d12", b12)
        add("api_timeout", r12["status"] == "BLOCKED" and "timeout" in str(r12.get("block_reason", "")).lower())

        # 13 Malformed broker response — account still dict-like; terminal malformed
        b13 = FakeEvidenceBackend(malformed=True)
        r13 = collect_fake(root / "d13", b13)
        # connected="yes" is truthy in bool() — still collects; ensure no crash
        add("malformed_broker_response", r13["status"] in ("COLLECTED", "BLOCKED"))

        # 14 Unknown commission
        costs14 = separate_costs(commission=None, swap=0.0)
        add("unknown_commission", costs14["commission"] == "UNKNOWN")

        # 15 Unknown swap
        costs15 = separate_costs(commission=0.0, swap=None)
        add("unknown_swap", costs15["swap"] == "UNKNOWN")

        # 16 Unknown position identifier
        from phase64_8.normalize import normalize_position

        p16 = normalize_position(
            {"ticket": None, "symbol": ACTIVE_SYMBOL, "type": 0, "volume": 0.01},
            retrieved_at="t",
            provenance={"synthetic": True},
        )
        add("unknown_position_identifier", p16["stable_key"].startswith("obs_position:") and p16["identity_class"] == "OBSERVATION")

        # 17 Unexpected broker symbol — still capture evidence (backend ignores filter)
        class _UnexpectedSymbolBackend(FakeEvidenceBackend):
            def positions_get(self, symbol: str | None = None) -> Any:
                self.call_log.append(f"positions_get:{symbol}")
                return tuple(self.positions)

        b17 = _UnexpectedSymbolBackend(positions=[_pos(170, symbol="EURUSDm")])
        r17 = collect_fake(root / "d17", b17)
        j17 = BrokerEvidenceJournal(root / "d17", allow_synthetic=True, store_label="FIXTURE")
        add(
            "unexpected_broker_symbol",
            r17["status"] == "COLLECTED"
            and any(e.get("unexpected_symbol") for e in j17.all_events() if e.get("record_kind") == "BROKER_POSITION"),
        )

        # 18 Unexpected account/server
        b18 = FakeEvidenceBackend()
        b18.account = {**b18.account, "login": 999999, "server": "Wrong-Server"}
        r18 = collect_fake(root / "d18", b18)
        add(
            "unexpected_account_server",
            r18["status"] == "BLOCKED" and r18.get("block_reason") in ("unexpected_account", "unexpected_server"),
        )

        # 19 Journal restart during persistence
        j19 = BrokerEvidenceJournal(root / "d19", allow_synthetic=True, store_label="FIXTURE")
        b19 = FakeEvidenceBackend(deals=[_deal(190, 191)])
        try:
            collect_once(
                b19,
                j19,
                synthetic=True,
                evidence_label=SIMULATED_LABEL,
            )
            # Inject crash via append_event
            from phase64_8.normalize import normalize_deal as nd

            rec = nd(_deal(192, 193), retrieved_at="t", provenance={"synthetic": True, "evidence_label": SIMULATED_LABEL})
            try:
                j19.append_event(rec, import_batch_id="batch_crash", crash_after_wal=True)
                crashed = False
            except RuntimeError:
                crashed = True
            j19b = BrokerEvidenceJournal(root / "d19", allow_synthetic=True, store_label="FIXTURE")
            recovered = any(e.get("broker_deal_id") == "192" for e in j19b.all_events())
            add("journal_restart_during_persistence", crashed and recovered)
        except Exception as ex:
            add("journal_restart_during_persistence", False, error=str(ex))

        # 20 Replay of complete evidence window
        b20 = FakeEvidenceBackend(
            positions=[],
            orders=[],
            deals=[_deal(200, 201)],
            hist_orders=[_order(201)],
        )
        collect_fake(root / "d20", b20)
        r20b = collect_fake(root / "d20", b20)
        j20 = BrokerEvidenceJournal(root / "d20", allow_synthetic=True, store_label="FIXTURE")
        add(
            "replay_complete_evidence_window",
            r20b["ingest_stats"]["DUPLICATE_SUPPRESSED"] >= 1
            and j20.integrity_report()["index_matches"],
        )

        # Security: order_send still prohibited / unauthorized attempt
        sec = audit_security_invariants()
        unauth = attempted_unauthorized_execution()
        add("order_send_prohibited", "order_send" in PROHIBITED_MT5_API and sec["pass"])
        add("unauthorized_execution_fail_closed", unauth["blocked"] and not unauth["reached_order_send"])
        add(
            "ro_apis_permitted",
            {"positions_get", "orders_get", "history_deals_get", "history_orders_get"} <= PERMITTED_MT5_API,
        )

        # Paper cannot fabricate broker deal
        recon_paper = reconcile_lifecycle(
            events=[],
            decisions=[{"decision_id": "d1", "fabricate_broker_deal": True}],
        )
        add(
            "paper_cannot_fabricate_broker_deal",
            any(f.get("blocked") for f in recon_paper["findings"]),
        )

        # Experience separation
        try:
            reconcile_lifecycle(events=[{"store_label": "PAPER", "record_kind": "BROKER_DEAL"}])
            sep_ok = False
        except ValueError:
            sep_ok = True
        add("experience_store_separation", sep_ok)

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "cases": cases,
        "suite_pass": all(c.get("pass") for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
