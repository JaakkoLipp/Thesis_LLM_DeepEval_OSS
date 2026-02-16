from __future__ import annotations

import os
from pathlib import Path

import pytest

import deepeval_mvp.service as service


def _fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


def test_process_fixture_file_stored(monkeypatch):
    fixture = _fixtures_dir() / "valid_sample.txt"

    class FakeStore:
        def __init__(self) -> None:
            self.saved = []
            self.skipped = []
            self.errors = []

        def claim_event(self, _event, owner_id):
            _ = owner_id
            return "evt-1", True

        def mark_done(self, event_id, event, evaluation):
            self.saved.append((event_id, event, evaluation))

        def mark_skipped(self, event_id, event):
            self.skipped.append((event_id, event))

        def mark_error(self, event_id, error_type, error_message):
            self.errors.append((event_id, error_type, error_message))

        def get_owner(self, event_id):
            _ = event_id
            return "owner-a"

    store = FakeStore()
    monkeypatch.setattr(
        service,
        "process_event",
        lambda event: {"metrics": [], "success": True},
    )

    status = service.process_fixture_file(fixture, store, owner_id="owner-a", run_mode="test")

    assert status == "stored"
    assert len(store.saved) == 1


def test_process_fixture_file_skipped(monkeypatch):
    fixture = _fixtures_dir() / "valid_sample.txt"

    class FakeStore:
        def claim_event(self, event, owner_id):
            _ = (event, owner_id)
            return "evt-1", True

        def mark_done(self, event_id, event, evaluation):
            raise AssertionError("mark_done should not be called for skipped event")

        def mark_skipped(self, event_id, event):
            _ = (event_id, event)

        def mark_error(self, event_id, error_type, error_message):
            raise AssertionError("mark_error should not be called for skipped event")

        def get_owner(self, event_id):
            _ = event_id
            return "owner-a"

    monkeypatch.setattr(service, "process_event", lambda event: None)

    status = service.process_fixture_file(fixture, FakeStore(), owner_id="owner-a", run_mode="test")

    assert status == "skipped"


def test_process_fixture_file_error_on_invalid_fixture(monkeypatch):
    fixture = _fixtures_dir() / "this_file_does_not_exist.txt"

    class FakeStore:
        def claim_event(self, event, owner_id):
            _ = (event, owner_id)
            return "evt-1", True

        def mark_done(self, event_id, event, evaluation):
            raise AssertionError("mark_done should not be called on parse error")

        def mark_skipped(self, event_id, event):
            raise AssertionError("mark_skipped should not be called on parse error")

        def mark_error(self, event_id, error_type, error_message):
            _ = (event_id, error_type, error_message)

        def get_owner(self, event_id):
            _ = event_id
            return "owner-a"

    monkeypatch.setattr(
        service,
        "process_event",
        lambda event: {"metrics": [], "success": True},
    )

    status = service.process_fixture_file(fixture, FakeStore(), owner_id="owner-a", run_mode="test")

    assert status == "error"


def test_process_fixture_file_skips_when_duplicate_claim(monkeypatch):
    fixture = _fixtures_dir() / "valid_sample.txt"

    class FakeStore:
        def claim_event(self, event, owner_id):
            _ = (event, owner_id)
            return "evt-1", False

        def get_owner(self, event_id):
            _ = event_id
            return "owner-existing"

        def mark_done(self, event_id, event, evaluation):
            raise AssertionError("mark_done should not be called for duplicate")

        def mark_skipped(self, event_id, event):
            raise AssertionError("mark_skipped should not be called for duplicate")

        def mark_error(self, event_id, error_type, error_message):
            raise AssertionError("mark_error should not be called for duplicate")

    monkeypatch.setattr(service, "process_event", lambda event: {"metrics": [], "success": True})

    status = service.process_fixture_file(fixture, FakeStore(), owner_id="owner-a", run_mode="test")

    assert status == "skipped"


def test_run_service_processes_fixture_files_once(monkeypatch):
    fixtures_dir = _fixtures_dir()

    class FakeStore:
        pass

    processed: list[str] = []

    def fake_process_fixture_file(path, _store, owner_id, run_mode="service"):
        _ = (run_mode, owner_id)
        processed.append(path.name)
        return "stored"

    monkeypatch.setattr(service, "MongoResultStore", FakeStore)
    monkeypatch.setattr(service, "process_fixture_file", fake_process_fixture_file)

    rc = service.run_service(fixtures_dir=fixtures_dir, poll_seconds=0.0, max_cycles=2)

    expected = sorted(p.name for p in fixtures_dir.glob("*.txt"))
    assert rc == 0
    assert sorted(processed) == expected


def test_run_service_returns_error_when_fixtures_missing(monkeypatch, tmp_path):
    missing_dir = tmp_path / "missing"

    class FakeStore:
        pass

    monkeypatch.setattr(service, "MongoResultStore", FakeStore)

    rc = service.run_service(fixtures_dir=missing_dir, poll_seconds=0.0, max_cycles=1)

    assert rc == 1


@pytest.mark.integration
def test_demo_full_integration_fixture_flow_dry_run(monkeypatch):
    fixtures_dir = _fixtures_dir()

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

        def mark_error(self, event_id, error_type, error_message):
            _ = (event_id, error_type, error_message)

        def get_owner(self, event_id):
            _ = event_id
            return "owner-a"

    monkeypatch.setattr(service, "MongoResultStore", FakeStore)
    monkeypatch.setattr(
        service,
        "process_event",
        lambda event: {"metrics": [{"name": "DryRunMetric", "score": 1.0, "threshold": 0.7, "success": True, "reason": "mocked", "error": None}], "success": True}
        if event.system == "enterprise-rag-chatbot" and event.event_type == "ai-event"
        else None,
    )

    rc = service.run_service(fixtures_dir=fixtures_dir, poll_seconds=0.0, max_cycles=1)

    assert rc == 0


@pytest.mark.system
@pytest.mark.skipif(os.getenv("RUN_SYSTEM") != "1", reason="RUN_SYSTEM!=1")
@pytest.mark.skipif(not os.getenv("JUDGE_MODEL"), reason="JUDGE_MODEL not set")
def test_demo_full_system_fixture_flow_prints_progress(monkeypatch):
    fixtures_dir = _fixtures_dir()

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

        def mark_error(self, event_id, error_type, error_message):
            _ = (event_id, error_type, error_message)

        def get_owner(self, event_id):
            _ = event_id
            return "owner-a"

    monkeypatch.setattr(service, "MongoResultStore", FakeStore)

    rc = service.run_service(fixtures_dir=fixtures_dir, poll_seconds=0.0, max_cycles=1)

    assert rc == 0
