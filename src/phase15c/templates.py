"""Permission request templates. Do not send — documentation/readiness only."""

from __future__ import annotations

from typing import Any

from phase15c.constants import PROVIDERS


REQUIRED_ASKS = (
    "Authorized historical signal export (CSV/JSON preferred)",
    "Permission to store signals for internal research",
    "Independent historical performance evaluation / backtesting against market prices",
    "Publication timestamps and subsequent updates/edits/cancellations",
    "Data retention limits and deletion obligations",
    "Separate explicit permission for any AI/ML training, fine-tuning, validation, or benchmarking",
)


def request_template_for(provider: dict[str, str]) -> dict[str, Any]:
    subject = (
        f"Research permission request — XAUUSD signal data "
        f"({provider['display_name']} / {provider['handle']})"
    )
    body = f"""Dear {provider['display_name']} team,

We are conducting an offline research project (AIBOT) comparing independently evaluated
XAUUSD signal records against historical market prices. We are writing to request explicit
written permission before receiving or storing any of your signal content.

Please confirm, in writing, whether you authorize each of the following for provider
{provider['handle']} ({provider['provider_id']}):

1. Authorized historical signal export (CSV/JSON preferred), limited to XAUUSD signals.
2. Permission to store those signals in a private research archive.
3. Independent historical performance evaluation / backtesting against market prices
   (provider-claimed outcomes will not be relied upon).
4. Inclusion of original publication timestamps and subsequent updates, edits, and
   cancellations where available.
5. Any data retention limits, deletion obligations, or attribution requirements.
6. Separate, explicit permission for AI/ML training, fine-tuning, validation, or
   benchmarking using this content. If not granted, we will treat AI/ML use as forbidden.

Public channel visibility or promotional materials will not be treated as permission.
Authorization for one purpose (for example storage) will not be treated as authorization
for another (for example backtesting or AI/ML).

This message is a template only and has not been sent.

Respectfully,
AIBOT Research
"""
    return {
        "provider_id": provider["provider_id"],
        "display_name": provider["display_name"],
        "handle": provider["handle"],
        "subject": subject,
        "body": body.strip() + "\n",
        "explicit_asks": list(REQUIRED_ASKS),
        "sent": False,
        "delivery_channel": None,
    }


def all_request_templates() -> dict[str, Any]:
    templates = [request_template_for(p) for p in PROVIDERS]
    return {
        "templates_sent": False,
        "provider_contact_attempted": False,
        "required_asks": list(REQUIRED_ASKS),
        "templates": templates,
    }
