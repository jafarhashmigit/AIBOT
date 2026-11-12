"""Deterministic fake broker backend — synthetic only; never genuine broker evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from phase64_9.constants import ACTIVE_SYMBOL, SIMULATED_LABEL, canonical_json_sha256


@dataclass
class FakeBrokerBackend:
    """
    Controllable broker simulator for execution FSM tests.
    All responses marked synthetic.
    """

    mode: str = "accept_full_fill"
    next_order_id: int = 1000
    next_deal_id: int = 5000
    call_log: list[dict[str, Any]] = field(default_factory=list)
    submitted: list[dict[str, Any]] = field(default_factory=list)

    def submit_order(self, request: dict[str, Any]) -> dict[str, Any]:
        self.call_log.append({"op": "submit_order", "request": dict(request)})
        self.submitted.append(dict(request))
        mode = self.mode

        if mode == "disconnect":
            return self._wrap({"status": "DISCONNECT", "retcode": -1, "accepted": False})

        if mode == "timeout_before_accept":
            return self._wrap({"status": "TIMEOUT", "phase": "before_accept", "accepted": False, "unknown": True})

        if mode == "timeout_after_accept":
            oid = self._alloc_order()
            return self._wrap(
                {
                    "status": "TIMEOUT",
                    "phase": "after_accept",
                    "accepted": True,
                    "unknown": True,
                    "order": oid,
                    "deal": None,
                    "note": "broker_may_have_accepted",
                }
            )

        if mode == "malformed":
            return self._wrap({"status": "MALFORMED", "raw": "???notjson", "accepted": False})

        if mode == "wrong_symbol":
            return self._wrap(
                {
                    "status": "REJECTED",
                    "retcode": 10014,
                    "comment": "invalid_symbol",
                    "accepted": False,
                    "requested_symbol": request.get("symbol"),
                    "expected": ACTIVE_SYMBOL,
                }
            )

        if mode == "invalid_volume":
            return self._wrap({"status": "REJECTED", "retcode": 10014, "comment": "invalid_volume", "accepted": False})

        if mode == "invalid_sl_tp":
            return self._wrap({"status": "REJECTED", "retcode": 10016, "comment": "invalid_stops", "accepted": False})

        if mode == "broker_reject":
            return self._wrap({"status": "REJECTED", "retcode": 10006, "comment": "rejected", "accepted": False})

        if mode == "duplicate_response":
            oid = self._alloc_order()
            did = self._alloc_deal()
            base = {
                "status": "ACCEPTED",
                "retcode": 10009,
                "order": oid,
                "deal": did,
                "volume": request.get("volume"),
                "price": request.get("price"),
                "accepted": True,
                "duplicate_of": oid,
            }
            # Caller may invoke twice; same ids if we don't re-alloc — simulate by fixing ids
            self.next_order_id = oid
            self.next_deal_id = did
            return self._wrap(base)

        if mode == "partial_fill":
            oid = self._alloc_order()
            d1 = self._alloc_deal()
            d2 = self._alloc_deal()
            vol = float(request.get("volume") or 0.02)
            return self._wrap(
                {
                    "status": "PARTIAL_FILL",
                    "retcode": 10009,
                    "order": oid,
                    "deals": [
                        {"deal": d1, "volume": vol / 2, "price": request.get("price")},
                        {"deal": d2, "volume": vol / 2, "price": request.get("price")},
                    ],
                    "deal": d1,
                    "volume_filled": vol,
                    "accepted": True,
                    "partial": True,
                }
            )

        if mode == "full_fill":
            oid = self._alloc_order()
            did = self._alloc_deal()
            return self._wrap(
                {
                    "status": "FILLED",
                    "retcode": 10009,
                    "order": oid,
                    "deal": did,
                    "volume": request.get("volume"),
                    "price": request.get("price"),
                    "accepted": True,
                }
            )

        if mode == "accepted_missing_deal":
            oid = self._alloc_order()
            return self._wrap(
                {
                    "status": "ACCEPTED",
                    "retcode": 10009,
                    "order": oid,
                    "deal": None,
                    "accepted": True,
                    "deal_delayed": False,
                    "missing_deal": True,
                }
            )

        if mode == "accepted_delayed_deal":
            oid = self._alloc_order()
            return self._wrap(
                {
                    "status": "ACCEPTED",
                    "retcode": 10009,
                    "order": oid,
                    "deal": None,
                    "accepted": True,
                    "deal_delayed": True,
                    "pending_deal_id": self._alloc_deal(),
                }
            )

        if mode == "multiple_deals":
            oid = self._alloc_order()
            deals = [self._alloc_deal() for _ in range(3)]
            return self._wrap(
                {
                    "status": "FILLED",
                    "order": oid,
                    "deals": [{"deal": d, "volume": 0.01} for d in deals],
                    "deal": deals[0],
                    "accepted": True,
                    "multiple_deals": True,
                }
            )

        # default accept_full_fill
        oid = self._alloc_order()
        did = self._alloc_deal()
        return self._wrap(
            {
                "status": "FILLED",
                "retcode": 10009,
                "order": oid,
                "deal": did,
                "volume": request.get("volume"),
                "price": request.get("price"),
                "accepted": True,
            }
        )

    def _alloc_order(self) -> int:
        oid = self.next_order_id
        self.next_order_id += 1
        return oid

    def _alloc_deal(self) -> int:
        did = self.next_deal_id
        self.next_deal_id += 1
        return did

    def _wrap(self, body: dict[str, Any]) -> dict[str, Any]:
        out = {
            **body,
            "synthetic": True,
            "evidence_label": SIMULATED_LABEL,
            "not_genuine_broker_evidence": True,
            "order_send_invoked": False,
        }
        out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
        return out


def run_fake_broker_suite() -> dict[str, Any]:
    modes = [
        "accept_full_fill",
        "broker_reject",
        "partial_fill",
        "full_fill",
        "duplicate_response",
        "timeout_after_accept",
        "timeout_before_accept",
        "malformed",
        "disconnect",
        "wrong_symbol",
        "invalid_volume",
        "invalid_sl_tp",
        "accepted_missing_deal",
        "accepted_delayed_deal",
        "multiple_deals",
    ]
    cases = []
    req = {
        "intent_id": "i1",
        "decision_id": "d1",
        "symbol": ACTIVE_SYMBOL,
        "direction": "BUY",
        "volume": 0.02,
        "price": 2650.0,
        "sl": 2649.0,
        "tp": 2652.0,
    }
    for m in modes:
        backend = FakeBrokerBackend(mode=m)
        r = backend.submit_order(req)
        ok = r.get("synthetic") is True and r.get("not_genuine_broker_evidence") is True and not r.get("order_send_invoked")
        cases.append({"mode": m, "pass": ok, "status": r.get("status")})
    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c["pass"]),
        "cases": cases,
        "suite_pass": all(c["pass"] for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
