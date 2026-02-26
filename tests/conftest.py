"""Shared fixtures for the deepeval-mvp test suite."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from deepeval_mvp.models import AIEvent


# ── Common AIEvent factory ────────────────────────────────────────────────────

@pytest.fixture
def sample_aievent() -> AIEvent:
    """Minimal valid AIEvent for unit tests."""
    return AIEvent(
        system="enterprise-rag-chatbot",
        event_type="ai-event",
        user_input="What is the capital of France?",
        context="France is a country in Europe. Its capital is Paris.",
        output="The capital of France is Paris.",
        raw_meta={
            "system": "enterprise-rag-chatbot",
            "event_type": "ai-event",
            "session_id": "sess-001",
            "time_stamp": "2026-02-23T00:00:00Z",
            "kafka": {"topic": "llm-events", "partition": 1, "offset": 42},
        },
    )


@pytest.fixture
def sample_aievent_no_kafka() -> AIEvent:
    """AIEvent without Kafka metadata (fixture/payload-derived ID path)."""
    return AIEvent(
        system="test-system",
        event_type="ai-event",
        user_input="hello",
        context="ctx",
        output="world",
        raw_meta={
            "system": "test-system",
            "event_type": "ai-event",
            "session_id": "s1",
            "time_stamp": "2026-02-23T00:00:00Z",
        },
    )


# ── Fixture file paths ───────────────────────────────────────────────────────

@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the tests/fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_fixture_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "valid_sample.txt"


# ── FakeMongoResultStore ─────────────────────────────────────────────────────

class FakeMongoResultStore:
    """In-memory stand-in for MongoResultStore.

    Implements the ``ResultStore`` protocol used by the service layer.
    Uses the real ``MongoResultStore.compute_event_id`` logic (imported lazily)
    so deduplication tests verify production behaviour.

    Note for the production fork: replace the ``_compute_event_id`` body with
    whatever deterministic ID logic your CosmosDB store uses.
    """

    def __init__(self) -> None:
        self.claimed_ids: set[str] = set()
        self.docs: dict[str, dict[str, Any]] = {}
        self.events: list[tuple[str, str]] = []  # (action, event_id)

    @staticmethod
    def _compute_event_id(event: AIEvent) -> str:
        """Delegate to real production ID logic.

        Imported lazily so the fake can be defined even when ``store_mongo``
        internals change — if the import fails, falls back to a simple hash.
        """
        try:
            from deepeval_mvp.store_mongo import (
                _kafka_id,
                _kafka_id_is_usable,
                _event_id_from_payload,
            )
            kid = _kafka_id(event.raw_meta)
            if kid and _kafka_id_is_usable(kid):
                return kid
            return _event_id_from_payload(event.raw_meta, event.user_input, event.output)
        except ImportError:
            import hashlib
            digest = hashlib.sha256(repr(event).encode("utf-8")).hexdigest()
            return f"fake:{digest}"

    def claim_event(self, event: AIEvent, owner_id: str) -> tuple[str, bool]:
        event_id = self._compute_event_id(event)
        if event_id in self.claimed_ids:
            self.events.append(("duplicate", event_id))
            return event_id, False

        self.claimed_ids.add(event_id)
        self.docs[event_id] = {
            "status": "processing",
            "owner_id": owner_id,
            "event": event,
            "evaluation": None,
            "error": None,
        }
        self.events.append(("claim", event_id))
        return event_id, True

    def mark_done(self, event_id: str, event: AIEvent, evaluation: dict[str, Any]) -> None:
        self.docs.setdefault(event_id, {})
        self.docs[event_id]["status"] = "done"
        self.docs[event_id]["evaluation"] = evaluation
        self.events.append(("done", event_id))

    def release_claim(self, event_id: str) -> None:
        self.claimed_ids.discard(event_id)
        self.docs.pop(event_id, None)
        self.events.append(("released", event_id))

    def mark_skipped(self, event_id: str, event: AIEvent, reason: str = "filtered_out") -> None:
        self.docs.setdefault(event_id, {})
        self.docs[event_id]["status"] = "skipped"
        self.docs[event_id]["skip_reason"] = reason
        self.events.append(("skipped", event_id))

    def mark_error(
        self,
        event_id: str,
        error_type: str,
        error_message: str,
        *,
        event: Any = None,
        traceback_text: str | None = None,
    ) -> None:
        self.docs.setdefault(event_id, {})
        self.docs[event_id]["status"] = "error"
        self.docs[event_id]["error"] = {"type": error_type, "message": error_message}
        if event is not None:
            self.docs[event_id]["event"] = event
        self.events.append(("error", event_id))


@pytest.fixture
def fake_store() -> FakeMongoResultStore:
    """Return a fresh FakeMongoResultStore."""
    return FakeMongoResultStore()
