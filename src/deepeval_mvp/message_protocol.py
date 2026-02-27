"""MessageSource protocol — the contract any message-ingestion adapter must satisfy.

Service-layer code depends on this protocol rather than on a concrete module,
enabling fixture sources in the MVP the same way ``ResultStore`` enables
in-memory fakes for storage.

When the production fork replaces ``get_message.py`` with a Kafka adapter,
the new module only needs to expose a class that satisfies ``MessageSource``.
"""
from __future__ import annotations

from typing import Any, Iterator, Protocol, TypedDict

from deepeval_mvp.models import AIEvent


class IncomingMessage(TypedDict, total=False):
    """Envelope handed from the message source to the service layer.

    ``raw`` is the only field that *must* be present.  ``kafka`` carries
    broker-side envelope metadata when available.  ``source_id`` is a
    human-readable fallback identifier used for diagnostics and deterministic
    error IDs when Kafka metadata is absent.
    """

    raw: bytes
    kafka: dict[str, Any]
    source_id: str


class MessageSource(Protocol):
    """Minimal interface that the service layer requires from its message source.

    Implementations MUST yield ``IncomingMessage`` dicts from ``iter_messages``
    and convert them to ``AIEvent`` instances via ``parse_event``.
    """

    def iter_messages(
        self,
        poll_seconds: float = 5.0,
        max_cycles: int | None = None,
    ) -> Iterator[IncomingMessage]:
        """Yield incoming messages from the configured source."""
        ...

    def parse_event(self, message: IncomingMessage) -> AIEvent:
        """Convert a raw incoming message to a validated ``AIEvent``."""
        ...
