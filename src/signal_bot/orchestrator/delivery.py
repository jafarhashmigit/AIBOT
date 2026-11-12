"""Discord delivery adapter — reuses phase16b client; modes isolate network."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from phase16b.client import post_webhook
from phase16b.secrets import load_webhook_url, redact_secrets, safe_config_status, webhook_configured
from signal_bot.orchestrator.constants import (
    DEAD_LETTER_PATH,
    DEFAULT_MODE,
    DELIVERY_LEDGER_PATH,
    DELIVERY_QUEUE_PATH,
    HARD_BLOCK_ACTIONABLE_DISCORD,
    MODE_AUTHORIZED,
    MODE_DISABLED,
    MODE_DRY_RUN,
    MODE_SHADOW,
)
from signal_bot.orchestrator.formatter import format_signal_message

Transport = Callable[[str, bytes, float], tuple[int, str]]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _atomic_write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


class DeliveryLedger:
    """Restart-safe delivery ledger. SHADOW/DRY_RUN/SENT all suppress duplicates."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else DELIVERY_LEDGER_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") in {"SENT", "DRY_RUN", "SHADOW_RECORDED", "BLOCKED_RECORDED"}:
                key = row.get("dedupe_key")
                if key:
                    self._seen.add(str(key))

    def already_delivered(self, dedupe_key: str) -> bool:
        return dedupe_key in self._seen

    def record(self, *, dedupe_key: str, signal_id: str, result: dict[str, Any], payload_meta: dict[str, Any]) -> None:
        status = result.get("status")
        if status in {"SENT", "DRY_RUN", "SHADOW_RECORDED", "BLOCKED_RECORDED"}:
            self._seen.add(dedupe_key)
        row = {
            "dedupe_key": dedupe_key,
            "signal_id": signal_id,
            "message_type": payload_meta.get("message_type"),
            "status": status,
            "attempts": result.get("attempts"),
            "http_status": result.get("http_status"),
            "error": redact_secrets(str(result.get("error"))) if result.get("error") else None,
            "recorded_utc": _utc(),
            # never store webhook
        }
        _append_jsonl(self.path, row)


class DeliveryQueue:
    """Pending queue + dead letter — survives restart."""

    def __init__(
        self,
        queue_path: Path | None = None,
        dead_path: Path | None = None,
    ) -> None:
        self.queue_path = Path(queue_path) if queue_path else DELIVERY_QUEUE_PATH
        self.dead_path = Path(dead_path) if dead_path else DEAD_LETTER_PATH
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)

    def enqueue(self, item: dict[str, Any]) -> None:
        _append_jsonl(self.queue_path, {**item, "enqueued_utc": _utc(), "state": "PENDING"})

    def dead_letter(self, item: dict[str, Any], reason: str) -> None:
        _append_jsonl(
            self.dead_path,
            {**item, "dead_letter_utc": _utc(), "reason": redact_secrets(reason), "state": "DEAD"},
        )

    def pending_count(self) -> int:
        if not self.queue_path.is_file():
            return 0
        n = 0
        for line in self.queue_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("state") == "PENDING":
                n += 1
        return n

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self.queue_path.is_file():
            for line in self.queue_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return rows[-limit:]


def deliver_signal(
    event: dict[str, Any],
    *,
    mode: str = DEFAULT_MODE,
    ledger: DeliveryLedger | None = None,
    queue: DeliveryQueue | None = None,
    transport: Transport | None = None,
    gate_allowed: bool = False,
) -> dict[str, Any]:
    """
    Deliver according to mode.
    AUTHORIZED path still requires gate_allowed=True; Prompt 6 clamps mode away from AUTHORIZED.
    Never logs webhook URL.
    """
    ledger = ledger or DeliveryLedger()
    queue = queue or DeliveryQueue()
    mode = str(mode or DEFAULT_MODE).upper()
    payload = format_signal_message(event, gated=not gate_allowed)
    dedupe_key = str(payload["dedupe_key"])
    signal_id = str(event.get("signal_id"))

    if ledger.already_delivered(dedupe_key):
        return {
            "status": "SKIPPED_DUPLICATE",
            "dedupe_key": dedupe_key,
            "network_called": False,
            "mode": mode,
        }

    discord_payload = {"content": payload["content"]}
    if payload.get("embeds"):
        discord_payload["embeds"] = payload["embeds"]

    queue.enqueue(
        {
            "signal_id": signal_id,
            "dedupe_key": dedupe_key,
            "mode": mode,
            "message_type": payload.get("message_type"),
            "gate_allowed": gate_allowed,
        }
    )

    if mode == MODE_DISABLED:
        result = {"status": "SKIPPED_DISABLED", "attempts": 0, "http_status": None, "error": None}
        ledger.record(dedupe_key=dedupe_key, signal_id=signal_id, result=result, payload_meta=payload)
        return {**result, "network_called": False, "mode": mode, "payload_preview": payload["content"][:500]}

    if mode in {MODE_DRY_RUN, MODE_SHADOW} or not gate_allowed:
        # SHADOW/DRY_RUN never contact Discord. Blocked actionable also recorded locally only.
        status = "SHADOW_RECORDED" if mode == MODE_SHADOW else "DRY_RUN"
        if not gate_allowed and str(event.get("direction")).upper() in {"BUY", "SELL"}:
            status = "BLOCKED_RECORDED"
        result = {"status": status, "attempts": 0, "http_status": None, "error": None}
        ledger.record(dedupe_key=dedupe_key, signal_id=signal_id, result=result, payload_meta=payload)
        return {
            **result,
            "network_called": False,
            "mode": mode,
            "payload_preview": payload["content"][:800],
            "webhook_configured": webhook_configured(),
            "config": safe_config_status(),
        }

    # AUTHORIZED + gate_allowed only — still refuse if webhook missing
    if mode != MODE_AUTHORIZED or not gate_allowed:
        result = {
            "status": "BLOCKED_RECORDED",
            "attempts": 0,
            "http_status": None,
            "error": "authorized_path_refused",
        }
        ledger.record(dedupe_key=dedupe_key, signal_id=signal_id, result=result, payload_meta=payload)
        return {**result, "network_called": False, "mode": mode}

    # Hard safety: never network-send actionable BUY/SELL while lock engaged
    msg_type = str(payload.get("message_type") or "")
    if HARD_BLOCK_ACTIONABLE_DISCORD and (
        msg_type.startswith("ACTIONABLE_")
        or str(event.get("direction") or "").upper() in {"BUY", "SELL"}
    ):
        result = {
            "status": "HARD_BLOCKED_ACTIONABLE",
            "attempts": 0,
            "http_status": None,
            "error": "hard_block_actionable_discord",
        }
        ledger.record(dedupe_key=dedupe_key, signal_id=signal_id, result=result, payload_meta=payload)
        return {**result, "network_called": False, "mode": mode}

    url = load_webhook_url()
    if not url:
        result = {"status": "FAILED_CONFIG", "attempts": 0, "http_status": None, "error": "missing_webhook"}
        ledger.record(dedupe_key=dedupe_key, signal_id=signal_id, result=result, payload_meta=payload)
        queue.dead_letter({"signal_id": signal_id, "dedupe_key": dedupe_key}, "missing_webhook")
        return {**result, "network_called": False, "mode": mode}

    try:
        result = post_webhook(url, discord_payload, transport=transport)
    except Exception as exc:
        result = {
            "status": "FAILED_HTTP",
            "attempts": 1,
            "http_status": 0,
            "error": redact_secrets(type(exc).__name__),
        }
        queue.dead_letter({"signal_id": signal_id, "dedupe_key": dedupe_key}, str(result["error"]))
    if result.get("error"):
        result["error"] = redact_secrets(str(result["error"]))
    ledger.record(dedupe_key=dedupe_key, signal_id=signal_id, result=result, payload_meta=payload)
    if result.get("status") != "SENT":
        queue.dead_letter({"signal_id": signal_id, "dedupe_key": dedupe_key, "result": result}, result.get("status") or "fail")
    return {**result, "network_called": True, "mode": mode}
