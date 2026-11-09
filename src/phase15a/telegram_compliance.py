"""Telegram ToS / API compliance summary for Phase 15A (audit only).

Sources inspected via official public pages (not channel content):
- https://telegram.org/tos/content-licensing
- https://core.telegram.org/api/terms
- https://telegram.org/tos/bot-developers
- https://core.telegram.org/bots/api
"""

from __future__ import annotations

from typing import Any


def telegram_compliance_findings() -> dict[str, Any]:
    return {
        "sources_reviewed": [
            {
                "url": "https://telegram.org/tos/content-licensing",
                "title": "Telegram Content Licensing",
                "key_restrictions": [
                    "Accessing Telegram content for purposes other than ordinary intended use is prohibited.",
                    "Scraping or harvesting content for AI/ML training, fine-tuning, validation, or benchmarking is prohibited unless every relevant user gives explicit, informed, affirmative, continued consent limited to specific content/chat.",
                    "Consent must be non-transferable and limited; platform-level scraping permission is not implied by public visibility.",
                ],
            },
            {
                "url": "https://core.telegram.org/api/terms",
                "title": "Telegram API Terms of Service",
                "key_restrictions": [
                    "Using, accessing, or aggregating Telegram data for AI/ML purposes is restricted under API terms aligned with content-licensing rules.",
                    "Client/API use must comply with Telegram ToS; unauthorized bulk extraction is not an authorized use.",
                ],
            },
            {
                "url": "https://telegram.org/tos/bot-developers",
                "title": "Telegram Bot Developer Terms",
                "key_restrictions": [
                    "Data collection for large datasets, ML models, or AI products is prohibited.",
                    "Scraping public group or channel contents for those purposes is prohibited.",
                    "Bots must not circumvent access controls or harvest channel history without authorization.",
                ],
            },
            {
                "url": "https://core.telegram.org/bots/api",
                "title": "Telegram Bot API",
                "key_restrictions": [
                    "getUpdates retains updates for a short window (documented ~24 hours); it is not a historical channel archive API.",
                    "Bot API does not provide a general getChatHistory / bulk historical channel dump for research harvesting.",
                    "Forward-looking bot receipt of messages requires the bot to be added/authorized in the chat; that is not equivalent to owner permission for research storage/backtesting.",
                ],
            },
        ],
        "phase15a_prohibited_actions": [
            "Scrape channel history",
            "Build bulk datasets from channel messages",
            "Use unofficial Telegram clients or user APIs to harvest messages",
            "Use Bot API for historical channel extraction",
            "Train/fine-tune/validate/benchmark AI/ML on Telegram-derived data without explicit required permissions",
            "Circumvent channel access restrictions",
            "Join paid groups or purchase subscriptions for this audit",
            "Store channel content without authorized purpose and permission",
        ],
        "uncertainties": [
            "Public visibility of a channel does not establish research, archival, or backtesting rights.",
            "Whether independent performance evaluation of human signals (without AI/ML training) still requires owner consent under 'ordinary intended use' is unresolved without counsel; Phase 15A treats owner written permission as required before any acquisition.",
            "Deleted-message and edit history availability and permission scope vary by channel and are unverified without authorized access.",
            "Third-party websites republishing signal screenshots are not an authorized AIBOT data source.",
        ],
        "default_legal_posture": "PERMISSION_REQUIRED",
        "ai_ml_use_default": "FORBIDDEN_WITHOUT_EXPLICIT_CONSENT",
        "scraping_default": "FORBIDDEN",
    }


def written_permission_must_cover() -> list[dict[str, str]]:
    return [
        {
            "topic": "historical_message_access",
            "must_cover": (
                "Explicit grant to access and receive historical XAUUSD signal messages "
                "(or an owner-supplied export) for the named research purpose."
            ),
        },
        {
            "topic": "signal_storage_and_retention",
            "must_cover": (
                "Permission to store signal text/structured fields, retention period, "
                "deletion obligations, and whether raw message bodies may be retained."
            ),
        },
        {
            "topic": "backtesting_and_performance_evaluation",
            "must_cover": (
                "Permission to compare signals against independent market prices and "
                "compute fill/outcome statistics for internal research."
            ),
        },
        {
            "topic": "edits_and_deleted_message_history",
            "must_cover": (
                "Whether edited and deleted messages may be retained/replayed; "
                "how updates and cancellations should be treated."
            ),
        },
        {
            "topic": "sharing_derived_statistics",
            "must_cover": (
                "Whether derived performance summaries may be shared internally, "
                "externally, or publicly; attribution requirements."
            ),
        },
        {
            "topic": "ai_ml_use",
            "must_cover": (
                "Separate explicit consent if any AI/ML training, fine-tuning, validation, "
                "or benchmarking will use Telegram-derived content. Absent that grant, "
                "AI/ML use remains forbidden under Telegram content-licensing rules."
            ),
        },
    ]
