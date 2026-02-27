"""ResultStore protocol — the contract any evaluation-result store must satisfy.

Service-layer code depends on this protocol rather than on a concrete class,
enabling in-memory fakes in tests and alternative backends in production.
"""
from __future__ import annotations

from typing import Any, Protocol

from deepeval_mvp.models import AIEvent


class ResultStore(Protocol):
    """Minimal interface that the service layer requires from its store."""

    def claim_event(self, event: AIEvent, owner_id: str) -> tuple[str, bool]:
        """Atomically claim *event*.  Returns ``(event_id, was_claimed)``."""
        ...

    def release_claim(self, event_id: str) -> None:
        """Release a previously-claimed event (e.g. when ``store_only_fails`` skips it)."""
        ...

    def mark_done(self, event_id: str, event: AIEvent, evaluation: dict[str, Any]) -> None:
        """Persist a completed evaluation result."""
        ...

    def mark_error(
        self,
        event_id: str,
        error_type: str,
        error_message: str,
        *,
        event: AIEvent | None = None,
        traceback_text: str | None = None,
    ) -> None:
        """Persist an error record."""
        ...
