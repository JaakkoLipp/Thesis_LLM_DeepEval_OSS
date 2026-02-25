from __future__ import annotations

from deepeval_mvp.env_utils import env_csv


def allowed_systems() -> set[str]:
    """Read ALLOWED_SYSTEMS from env at call time (supports dotenv & runtime reconfiguration)."""
    return set(env_csv("ALLOWED_SYSTEMS", "enterprise-rag-chatbot,test-system"))


def allowed_event_types() -> set[str]:
    """Read ALLOWED_EVENT_TYPES from env at call time."""
    return set(env_csv("ALLOWED_EVENT_TYPES", "ai-event"))


def should_evaluate(system: str, event_type: str) -> bool:
    """Return True if this system/event_type pair should be sent for LLM evaluation."""
    return system in allowed_systems() and event_type in allowed_event_types()

