from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class AIEvent:
    system: str
    event_type: str
    user_input: str
    context: str
    output: str
    raw_meta: dict[str, Any]
