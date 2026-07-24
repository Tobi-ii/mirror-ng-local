"""
temporal.py — Multi-tiered temporal context resolution for the AI agent.
Resolves date bounds via: Active viewport → Onboarding profile → System default.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

SOURCE_VIEWPORT = "Dashboard date filter"
SOURCE_ONBOARDING = "Onboarding audit window"
SOURCE_SYSTEM = "System default (full history)"


def get_agent_temporal_context(
    user_id: str,
    payload_since: Optional[str],
    payload_until: Optional[str],
    db_conn
) -> dict:
    """
    Resolve absolute temporal anchor for the LLM.

    Priority:
    1. Active viewport dates from the UI (payload_since/payload_until)
    2. Onboarding audit window from user profile (DB)
    3. System default fallback
    """
    # Tier 1: Active viewport from UI
    if payload_since and payload_until:
        return {
            "since": payload_since,
            "until": payload_until,
            "source": SOURCE_VIEWPORT
        }

    # Tier 2: Onboarding profile baseline from DB
    try:
        cursor = db_conn.execute(
            'SELECT onboarding_start_date, onboarding_end_date FROM users WHERE user_id = ?',
            (user_id,)
        )
        row = cursor.fetchone()
        if row and row['onboarding_start_date'] and row['onboarding_end_date']:
            return {
                "since": row['onboarding_start_date'],
                "until": row['onboarding_end_date'],
                "source": SOURCE_ONBOARDING
            }
    except Exception as e:
        logger.debug(f"Could not read onboarding dates for user {user_id}: {e}")

    # If we have payload_since but no payload_until, still use it as a lower bound
    if payload_since:
        return {
            "since": payload_since,
            "until": datetime.utcnow().strftime("%Y-%m-%d"),
            "source": SOURCE_VIEWPORT
        }

    # Tier 3: System default
    return {
        "since": "2026-01-01",
        "until": datetime.utcnow().strftime("%Y-%m-%d"),
        "source": SOURCE_SYSTEM
    }
