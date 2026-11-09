"""Discord webhook HTTP client. Stdlib only. Secrets never logged."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from phase16b.constants import (
    HTTP_MAX_ATTEMPTS,
    HTTP_RETRY_BACKOFF_SECONDS,
    HTTP_TIMEOUT_SECONDS,
)
from phase16b.secrets import redact_secrets

Transport = Callable[[str, bytes, float], tuple[int, str]]


def _default_transport(url: str, body: bytes, timeout: float) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            # Discord may reject default urllib User-Agent with HTTP 403.
            "User-Agent": "AIBOT-Phase16B/1.0 (notification-only; read-only)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), redact_secrets(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        return int(exc.code), redact_secrets(raw)
    except Exception as exc:
        # Timeouts / connection errors
        return 0, redact_secrets(f"{type(exc).__name__}")


def post_webhook(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    timeout: float = HTTP_TIMEOUT_SECONDS,
    max_attempts: int = HTTP_MAX_ATTEMPTS,
    backoff: tuple[float, ...] = HTTP_RETRY_BACKOFF_SECONDS,
    transport: Transport | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """POST JSON payload with bounded retries. Never includes URL in result."""
    if not webhook_url:
        return {
            "status": "FAILED_CONFIG",
            "attempts": 0,
            "http_status": None,
            "error": "missing_webhook",
            "changed_decision": False,
        }
    send = transport or _default_transport
    sleeper = sleep_fn or time.sleep
    body = json.dumps(payload).encode("utf-8")
    attempts = 0
    last_status = None
    last_error = None
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        try:
            http_status, _resp_text = send(webhook_url, body, timeout)
            last_status = http_status
            if 200 <= http_status < 300:
                return {
                    "status": "SENT",
                    "attempts": attempts,
                    "http_status": http_status,
                    "error": None,
                    "changed_decision": False,
                }
            last_error = f"http_{http_status}"
            # Retry on 429/5xx; fail-fast on other 4xx
            if http_status and http_status < 500 and http_status != 429:
                break
        except Exception as exc:
            last_status = 0
            last_error = redact_secrets(type(exc).__name__)
        if attempt < max_attempts:
            delay = backoff[min(attempt - 1, len(backoff) - 1)] if backoff else 0.0
            if delay > 0:
                sleeper(delay)
    return {
        "status": "FAILED_HTTP",
        "attempts": attempts,
        "http_status": last_status,
        "error": last_error or "delivery_failed",
        "changed_decision": False,
    }
