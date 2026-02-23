from __future__ import annotations

import os

import pytest

import deepeval_mvp.service as service
from deepeval_mvp.models import AIEvent


def _sample_event() -> AIEvent:
    return AIEvent(
        system="enterprise-rag-chatbot",
        event_type="ai-event",
        user_input="hello",
        context="ctx",
        output="world",
        raw_meta={
            "system": "enterprise-rag-chatbot",
            "event_type": "ai-event",
            "session_id": "s1",
            "time_stamp": "2026-02-23T00:00:00Z",
            "kafka": {"topic": "t", "partition": 1, "offset": 2},
        },
    )


def test_process_incoming_event_stored(monkeypatch):
    event = _sample_event()

    class FakeStore:
        def __init__(self) -> None:
            self.saved = []

        def claim_event(self, _event, owner_id):
            _ = owner_id
            return "evt-1", True

        def mark_done(self, event_id, event, evaluation):
            self.saved.append((event_id, event, evaluation))

        def mark_skipped(self, event_id, _event):
            raise AssertionError("mark_skipped should not be called for stored event")

        def mark_error(self, event_id, *args):
            raise AssertionError("mark_error should not be called for stored event")

    store = FakeStore()
    monkeypatch.setattr(
        service,
        "process_event",
        lambda event: {"metrics": [], "success": True},
    )

    status = service.process_incoming_event(event, store, owner_id="owner-a", run_mode="test")

    assert status == "stored"
    assert len(store.saved) == 1


def test_process_incoming_event_skipped(monkeypatch):
    event = _sample_event()

    class FakeStore:
        def claim_event(self, _event, owner_id):
            _ = owner_id
            return "evt-1", True

        def mark_done(self, event_id, _event, evaluation):
            raise AssertionError("mark_done should not be called for skipped event")

        def mark_skipped(self, event_id, _event):
            _ = event_id

        def mark_error(self, event_id, *args):
            raise AssertionError("mark_error should not be called for skipped event")

    monkeypatch.setattr(service, "process_event", lambda event: None)

    status = service.process_incoming_event(event, FakeStore(), owner_id="owner-a", run_mode="test")

    assert status == "skipped"


def test_process_message_error_on_parse_failure():
    message = {"raw": b"not-json-and-not-kafka-wrapper", "source_id": "msg-1"}

    class FakeStore:
        def __init__(self) -> None:
            self.errors = []

        def mark_error(self, event_id, error_type, error_message):
            self.errors.append((event_id, error_type, error_message))

    store = FakeStore()
    status = service.process_message(message, store, owner_id="owner-a", run_mode="test")

    assert status == "error"
    assert len(store.errors) == 1


def test_process_incoming_event_skips_when_duplicate_claim(monkeypatch):
    event = _sample_event()

    class FakeStore:
        def claim_event(self, _event, owner_id):
            _ = owner_id
            return "evt-1", False

        def mark_done(self, event_id, _event, evaluation):
            raise AssertionError("mark_done should not be called for duplicate")

        def mark_skipped(self, event_id, _event):
            raise AssertionError("mark_skipped should not be called for duplicate")

        def mark_error(self, event_id, *args):
            raise AssertionError("mark_error should not be called for duplicate")

    monkeypatch.setattr(service, "process_event", lambda event: {"metrics": [], "success": True})

    status = service.process_incoming_event(event, FakeStore(), owner_id="owner-a", run_mode="test")

    assert status == "skipped"


def test_run_service_processes_messages(monkeypatch):
    messages = [
        {"raw": b'{"system":"enterprise-rag-chatbot","event_type":"ai-event","event_data":{"request":"a","response":{"output":"b"}},"retrieval_context":{"output":"c"}}', "source_id": "m1"},
        {"raw": b'{"system":"enterprise-rag-chatbot","event_type":"ai-event","event_data":{"request":"d","response":{"output":"e"}},"retrieval_context":{"output":"f"}}', "source_id": "m2"},
    ]

    class FakeStore:
        pass

    processed: list[str] = []

    def fake_iter_incoming_messages(poll_seconds: float = 5.0, max_cycles: int | None = None):
        _ = (poll_seconds, max_cycles)
        for msg in messages:
            yield msg

    def fake_process_message(message, _store, owner_id, run_mode="service"):
        _ = (run_mode, owner_id)
        processed.append(message["source_id"])
        return "stored"

    monkeypatch.setattr(service, "MongoResultStore", FakeStore)
    monkeypatch.setattr(service, "iter_incoming_messages", fake_iter_incoming_messages)
    monkeypatch.setattr(service, "process_message", fake_process_message)

    rc = service.run_service(poll_seconds=0.0, max_cycles=1)

    assert rc == 0
    assert sorted(processed) == ["m1", "m2"]


def test_run_service_returns_error_when_source_fails(monkeypatch):
    def boom(*args, **kwargs):
        _ = (args, kwargs)
        raise RuntimeError("source failed")

    class FakeStore:
        pass

    monkeypatch.setattr(service, "MongoResultStore", FakeStore)
    monkeypatch.setattr(service, "iter_incoming_messages", boom)

    rc = service.run_service(poll_seconds=0.0, max_cycles=1)

    assert rc == 1


@pytest.mark.integration
def test_demo_full_integration_fixture_flow_dry_run(monkeypatch):
    messages = [
        {"raw": b'{"system":"enterprise-rag-chatbot","event_type":"ai-event","event_data":{"request":"a","response":{"output":"b"}},"retrieval_context":{"output":"c"}}', "source_id": "m1"},
    ]

    def fake_iter_incoming_messages(poll_seconds: float = 5.0, max_cycles: int | None = None):
        _ = (poll_seconds, max_cycles)
        for msg in messages:
            yield msg

    class FakeStore:
        def __init__(self):
            self.saved = []

        def claim_event(self, event, owner_id):
            _ = (event, owner_id)
            event_id = f"evt-{len(self.saved) + 1}"
            return event_id, True

        def mark_done(self, event_id, event, evaluation):
            event_id = f"evt-{len(self.saved) + 1}"
            self.saved.append((event, evaluation, event_id))

        def mark_skipped(self, event_id, event):
            _ = (event_id, event)

        def mark_error(self, event_id, *args):
            _ = (event_id, args)

    monkeypatch.setattr(service, "MongoResultStore", FakeStore)
    monkeypatch.setattr(service, "iter_incoming_messages", fake_iter_incoming_messages)
    monkeypatch.setattr(
        service,
        "process_event",
        lambda event: {"metrics": [{"name": "DryRunMetric", "score": 1.0, "threshold": 0.7, "success": True, "reason": "mocked", "error": None}], "success": True}
        if event.system == "enterprise-rag-chatbot" and event.event_type == "ai-event"
        else None,
    )

    rc = service.run_service(poll_seconds=0.0, max_cycles=1)

    assert rc == 0


@pytest.mark.system
@pytest.mark.skipif(os.getenv("RUN_SYSTEM") != "1", reason="RUN_SYSTEM!=1")
@pytest.mark.skipif(not os.getenv("JUDGE_MODEL"), reason="JUDGE_MODEL not set")
def test_demo_full_system_fixture_flow_prints_progress(monkeypatch):
    messages = [
        {"raw": b'{"system":"enterprise-rag-chatbot","event_type":"ai-event","event_data":{"request":"a","response":{"output":"b"}},"retrieval_context":{"output":"c"}}', "source_id": "m1"},
    ]

    def fake_iter_incoming_messages(poll_seconds: float = 5.0, max_cycles: int | None = None):
        _ = (poll_seconds, max_cycles)
        for msg in messages:
            yield msg

    class FakeStore:
        def __init__(self):
            self.saved = []

        def claim_event(self, event, owner_id):
            _ = (event, owner_id)
            event_id = f"evt-{len(self.saved) + 1}"
            return event_id, True

        def mark_done(self, event_id, event, evaluation):
            event_id = f"evt-{len(self.saved) + 1}"
            self.saved.append((event, evaluation, event_id))

        def mark_skipped(self, event_id, event):
            _ = (event_id, event)

        def mark_error(self, event_id, *args):
            _ = (event_id, args)

    monkeypatch.setattr(service, "MongoResultStore", FakeStore)
    monkeypatch.setattr(service, "iter_incoming_messages", fake_iter_incoming_messages)

    rc = service.run_service(poll_seconds=0.0, max_cycles=1)

    assert rc == 0
