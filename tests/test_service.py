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

        def save(self, event, evaluation):
            self.saved.append((event, evaluation))
            return "evt-1"

    store = FakeStore()
    monkeypatch.setattr(
        service,
        "process_event",
        lambda event: {"metrics": [], "success": True},
    )

    status = service.process_fixture_file(fixture, store, run_mode="test")

    assert status == "stored"
    assert len(store.saved) == 1


def test_process_fixture_file_skipped(monkeypatch):
    fixture = _fixtures_dir() / "valid_sample.txt"

    class FakeStore:
        def save(self, event, evaluation):
            raise AssertionError("save should not be called for skipped event")

    monkeypatch.setattr(service, "process_event", lambda event: None)

    status = service.process_fixture_file(fixture, FakeStore(), run_mode="test")

    assert status == "skipped"


def test_process_fixture_file_error_on_invalid_fixture(monkeypatch):
    fixture = _fixtures_dir() / "this_file_does_not_exist.txt"

    class FakeStore:
        def save(self, event, evaluation):
            raise AssertionError("save should not be called on parse error")

    monkeypatch.setattr(
        service,
        "process_event",
        lambda event: {"metrics": [], "success": True},
    )

    status = service.process_fixture_file(fixture, FakeStore(), run_mode="test")

    assert status == "error"


def test_run_service_processes_fixture_files_once(monkeypatch):
    fixtures_dir = _fixtures_dir()

    class FakeStore:
        pass

    processed: list[str] = []

    def fake_process_fixture_file(path, _store, run_mode="service"):
        _ = run_mode
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

        def save(self, event, evaluation):
            event_id = f"evt-{len(self.saved) + 1}"
            self.saved.append((event, evaluation, event_id))
            return event_id

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

        def save(self, event, evaluation):
            event_id = f"evt-{len(self.saved) + 1}"
            self.saved.append((event, evaluation, event_id))
            return event_id

    monkeypatch.setattr(service, "MongoResultStore", FakeStore)

    rc = service.run_service(fixtures_dir=fixtures_dir, poll_seconds=0.0, max_cycles=1)

    assert rc == 0
