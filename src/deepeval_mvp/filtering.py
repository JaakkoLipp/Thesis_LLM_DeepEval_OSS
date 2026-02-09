from __future__ import annotations
import os

def _parse_csv_env(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip() for x in raw.split(",") if x.strip()}

ALLOWED_SYSTEMS = _parse_csv_env("ALLOWED_SYSTEMS", "enterprise-rag-chatbot,test-system")
ALLOWED_EVENT_TYPES = _parse_csv_env("ALLOWED_EVENT_TYPES", "ai-event")

def should_evaluate(system: str, event_type: str) -> bool:
    return (
        system in ALLOWED_SYSTEMS
        and event_type in ALLOWED_EVENT_TYPES
    )
