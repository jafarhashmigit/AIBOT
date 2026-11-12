"""Graceful shutdown and checkpoint helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase54.timeutil import now_utc_iso
from phase56.constants import CHECKPOINT_DIR
from phase56.progress import write_json


def graceful_shutdown(engine, *, reason: str = "CLI_STOP") -> dict[str, Any]:
    engine.shutting_down = True
    engine.persist()
    engine.hist.flush()
    engine.shadow.flush()
    if hasattr(engine, "observer") and engine.observer.registry:
        engine.observer.registry.save()
    ckpt = {
        "reason": reason,
        "iso": now_utc_iso(),
        "cursor": engine.state.data.get("cursor"),
        "open_positions": dict(engine.risk.open_positions),
        "pending_outcomes": list(getattr(engine, "pending_outcomes", []) or []),
        "closed_position_ids": list(engine.state.data.get("closed_position_ids") or []),
        "metrics": dict(getattr(engine, "metrics", {}) or {}),
        "feed_safety": engine.feed_safety.snapshot() if hasattr(engine, "feed_safety") else {},
        "last_candle": getattr(engine.observer, "last_success", None),
        "policy_version": getattr(engine.policy, "version", None),
    }
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKPOINT_DIR / "latest_checkpoint.json"
    write_json(path, ckpt)
    heartbeat = {
        "status": "STOPPED",
        "iso": now_utc_iso(),
        "reason": reason,
        "checkpoint": str(path),
    }
    write_json(CHECKPOINT_DIR / "heartbeat.json", heartbeat)
    return {"ok": True, "checkpoint": ckpt, "path": str(path), "heartbeat": heartbeat}


def load_checkpoint(path: Path | None = None) -> dict[str, Any] | None:
    p = path or (CHECKPOINT_DIR / "latest_checkpoint.json")
    if not p.is_file():
        return None
    import json

    return json.loads(p.read_text(encoding="utf-8"))
