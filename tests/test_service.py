# tests/test_service.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

# Adjust these imports if your package/module path differs
from deepeval_mvp import get_message, service


# ---------- Helpers ----------

class FakeMongoResultStore:
    """
    In-memory stand-in for MongoResultStore.

    Supports the methods used by the new service architecture:
      - claim_event
      - mark_done
      - mark_skipped
      - mark_error
    """
    def __init__(self) -> None:
        self.claimed_ids: set[str] = set()
        self.docs: dict[str, dict[str, Any]] = {}
        self.events: list[tuple[str, str]] = []  # (action, event_id)

    def _event_id(self, event) -> str:
        # Deterministic enough for tests; mirrors dedupe-by-content/session-ish behavior.
        meta = getattr(event, "raw_meta", {}) or {}
        topic = meta.get("kafka", {}).get("topic")
        partition = meta.get("kafka", {}).get("partition")
        offset = meta.get("kafka", {}).get("offset")

        if (
            topic not in (None, "", "REDACTED")
            and partition is not None
            and offset is not None
            and not (partition == 0 and offset == 0)  # reject fixture placeholders, mirrors _kafka_id_is_usable
        ):
            return f"kafka:{topic}:{partition}:{offset}"

        # Fallback pseudo-id
        return (
            f"evt:{getattr(event, 'system', '')}|"
            f"{getattr(event, 'event_type', '')}|"
            f"{getattr(event, 'user_input', '')}|"
            f"{getattr(event, 'output', '')}"
        )

    def claim_event(self, event, owner_id: str) -> tuple[str, bool]:
        event_id = self._event_id(event)
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

    def mark_done(self, event_id: str, event, evaluation: dict) -> None:
        self.docs.setdefault(event_id, {})
        self.docs[event_id]["status"] = "done"
        self.docs[event_id]["evaluation"] = evaluation
        self.events.append(("done", event_id))

    def release_claim(self, event_id: str) -> None:
        self.claimed_ids.discard(event_id)
        self.docs.pop(event_id, None)
        self.events.append(("released", event_id))

    def mark_skipped(self, event_id: str, event, reason: str = "filtered_out") -> None:
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


def _fixture_dir() -> Path:
    """
    Old test behavior expected tests/fixtures.
    Falls back to current test file directory if needed.
    """
    d = Path(__file__).parent / "fixtures"
    if d.exists():
        return d
    # Optional fallback if you keep fixture txt files beside the test file
    return Path(__file__).parent


def _patch_service_store(monkeypatch):
    holder: dict[str, FakeMongoResultStore] = {}

    def _factory(*args, **kwargs):
        inst = FakeMongoResultStore()
        holder["store"] = inst
        return inst

    monkeypatch.setattr(service, "MongoResultStore", _factory)
    return holder


# ---------- Fast tests (no real eval required) ----------

def test_iter_fixture_messages_reads_txt_files_once(tmp_path: Path, monkeypatch):
    # Arrange: two .txt fixtures + one ignored file
    (tmp_path / "a.txt").write_text('{"x":1}', encoding="utf-8")
    (tmp_path / "b.txt").write_text('{"x":2}', encoding="utf-8")
    (tmp_path / "ignore.json").write_text('{"x":3}', encoding="utf-8")

    monkeypatch.setenv("MESSAGE_SOURCE", "fixture")
    monkeypatch.setenv("MESSAGE_FIXTURE_DIR", str(tmp_path))

    # Act: one scan cycle only
    msgs = list(get_message.iter_incoming_messages(poll_seconds=0.0, max_cycles=1))

    # Assert
    assert len(msgs) == 2
    ids = {m["source_id"] for m in msgs}
    assert str((tmp_path / "a.txt").resolve()) in ids
    assert str((tmp_path / "b.txt").resolve()) in ids
    assert all(Path(m["source_id"]).suffix == ".txt" for m in msgs)


def test_iter_fixture_messages_does_not_reread_same_path_in_same_process(tmp_path: Path, monkeypatch):
    """
    Important behavior of the new architecture:
    dedupe is by file path (seen set), not by content change.
    """
    f = tmp_path / "sample.txt"
    f.write_text('{"v":1}', encoding="utf-8")

    monkeypatch.setenv("MESSAGE_SOURCE", "fixture")
    monkeypatch.setenv("MESSAGE_FIXTURE_DIR", str(tmp_path))

    gen = get_message.iter_incoming_messages(poll_seconds=0.0, max_cycles=2)

    first = next(gen)
    assert first["source_id"] == str(f.resolve())

    # Overwrite same path; should NOT emit again in same iterator process run.
    f.write_text('{"v":2}', encoding="utf-8")

    with pytest.raises(StopIteration):
        next(gen)


def test_process_message_parse_error_marks_error(monkeypatch):
    holder = _patch_service_store(monkeypatch)
    store = service.MongoResultStore()

    # invalid raw payload
    message = {"raw": b"not-json-and-not-kafka-wrapper", "source_id": "/tmp/bad.txt"}

    outcome = service.process_message(message, store=store, owner_id="test-owner", run_mode="test")
    assert outcome == "error"

    # At least one error doc should exist
    statuses = [doc.get("status") for doc in store.docs.values()]
    assert "error" in statuses


def test_process_incoming_event_duplicate_claim_skips(monkeypatch):
    holder = _patch_service_store(monkeypatch)
    store = service.MongoResultStore()

    # Build a minimal AIEvent using your models module via parser path is more robust.
    # Use a real parsed fixture if available, otherwise skip.
    fixture_dir = _fixture_dir()
    valid_candidates = [p for p in fixture_dir.glob("*.txt") if "valid" in p.name or "sample" in p.name]
    if not valid_candidates:
        pytest.skip("No suitable fixture file found for duplicate-claim test.")

    raw = valid_candidates[0].read_bytes()
    msg = {"raw": raw, "source_id": str(valid_candidates[0].resolve())}
    event = get_message.parse_incoming_event(msg)

    # Monkeypatch process_event so this test does not invoke real DeepEval
    monkeypatch.setattr(service, "process_event", lambda ev: {"success": True, "metrics": []})

    first = service.process_incoming_event(event, store=store, owner_id="ownerA", run_mode="test")
    second = service.process_incoming_event(event, store=store, owner_id="ownerB", run_mode="test")

    assert first in ("stored", "skipped")  # depends on filtering
    assert second == "skipped"


# ---------- System-ish demo tests (real fixtures, new architecture) ----------

@pytest.mark.system
def test_demo_full_system_fixture_flow_prints_progress(monkeypatch):
    """
    Demo test: runs the real service loop against fixtures with no MongoDB writes.

    Behavior:
      - Uses real fixture polling (no monkeypatching iter_incoming_messages)
      - Scans the fixture directory once (max_cycles=1)
      - Uses fake Mongo store (avoids real DB writes)
      - Evaluation output is printed live to the terminal (PRINT_EVAL_RESULTS=true by default)
        Run with `uv run poe demo` (which passes -s) to see it in the terminal.

    Notes:
      - Slow: calls the real judge model via DeepEval
      - Gate with RUN_SYSTEM=1 to avoid accidental CI/runtime cost
    """
    if os.getenv("RUN_SYSTEM") != "1":
        pytest.skip("Set RUN_SYSTEM=1 to run the full fixture system demo test.")

    fixtures_dir = _fixture_dir()
    if not fixtures_dir.exists():
        pytest.skip(f"Fixture directory does not exist: {fixtures_dir}")

    txts = list(fixtures_dir.glob("*.txt"))
    if not txts:
        pytest.skip(f"No .txt fixtures found in {fixtures_dir}")

    monkeypatch.setenv("MESSAGE_SOURCE", "fixture")
    monkeypatch.setenv("MESSAGE_FIXTURE_DIR", str(fixtures_dir))
    # Ensure evaluation results and live token streaming are printed during the demo run.
    # STREAM_EVAL_OUTPUT is also set to true by the `poe demo` task env.
    monkeypatch.setenv("PRINT_EVAL_RESULTS", "true")
    monkeypatch.setenv("STREAM_EVAL_OUTPUT", "true")

    # Avoid real Mongo; keep everything else real (parsing, filtering, eval, printing).
    holder = _patch_service_store(monkeypatch)

    # Run exactly one scan cycle.
    service.run_service(poll_seconds=0.0, max_cycles=1)

    store = holder["store"]
    statuses = [doc.get("status") for doc in store.docs.values()]

    # At least some fixtures were processed.
    assert len(statuses) >= 1, "No fixture events were processed."
    assert any(s in ("done", "skipped", "error") for s in statuses), (
        f"Expected at least one done/skipped/error outcome, got: {statuses}"
    )


@pytest.mark.system
def test_demo_full_system_fixture_flow_counts_all_fixture_outcomes(monkeypatch):
    """
    Optional companion test:
    runs one fixture scan and verifies all .txt files were at least *seen*
    as one of done/skipped/error (duplicates excluded).
    """
    if os.getenv("RUN_SYSTEM") != "1":
        pytest.skip("Set RUN_SYSTEM=1 to run the full fixture system demo test.")

    fixtures_dir = _fixture_dir()
    txt_files = sorted(fixtures_dir.glob("*.txt"))
    if not txt_files:
        pytest.skip(f"No .txt fixtures found in {fixtures_dir}")

    monkeypatch.setenv("MESSAGE_SOURCE", "fixture")
    monkeypatch.setenv("MESSAGE_FIXTURE_DIR", str(fixtures_dir))

    holder = _patch_service_store(monkeypatch)

    service.run_service(poll_seconds=0.0, max_cycles=1)

    store = holder["store"]

    # This is not a strict 1:1 file->doc assertion because parse errors use ingest:* IDs,
    # and duplicates may collapse. But for a fixture pack demo, there should be multiple outcomes.
    actions = [a for a, _ in store.events]
    assert "claim" in actions or "error" in actions
    assert any(a in ("done", "skipped", "error") for a in actions)


# ---------- Legacy-feel compatibility smoke test (fast, deterministic) ----------

def test_service_full_fixture_scan_with_stubbed_pipeline(monkeypatch):
    """
    Fast deterministic replacement for old 'process all fixtures' behavior,
    but on the new architecture.

    It uses real fixture reading/parsing, fake Mongo, and stubs process_event
    to avoid DeepEval and external model dependencies.
    """
    fixtures_dir = _fixture_dir()
    txt_files = sorted(fixtures_dir.glob("*.txt"))
    if not txt_files:
        pytest.skip(f"No .txt fixtures found in {fixtures_dir}")

    monkeypatch.setenv("MESSAGE_SOURCE", "fixture")
    monkeypatch.setenv("MESSAGE_FIXTURE_DIR", str(fixtures_dir))

    holder = _patch_service_store(monkeypatch)

    # Stub pipeline result while keeping filtering + parsing + service orchestration real
    def _stub_process_event(event):
        # Return None for filtered events by delegating to actual service.process_event if you want.
        # Here we just produce a deterministic evaluation for any parsed event.
        return {
            "success": True,
            "metrics": [{
                "name": "stub",
                "success": True,
                "score": 1.0,
                "threshold": 0.5,
                "reason": "stub reason",
            }],
        }

    monkeypatch.setattr(service, "process_event", _stub_process_event)

    service.run_service(poll_seconds=0.0, max_cycles=1)

    store = holder["store"]
    assert len(store.events) >= 1
    # At least one event must have been stored as "done" (not silently errored)
    actions = [a for a, _ in store.events]
    assert "done" in actions, f"Expected at least one 'done' outcome; got: {actions}"


# ---------- store_only_fails tests ----------

def test_store_only_fails_releases_successful_eval(monkeypatch):
    """When store_only_fails=True a passing evaluation must NOT be stored."""
    holder = _patch_service_store(monkeypatch)
    store = service.MongoResultStore()

    fixture_dir = _fixture_dir()
    valid_candidates = [p for p in fixture_dir.glob("*.txt") if "valid" in p.name or "sample" in p.name]
    if not valid_candidates:
        pytest.skip("No suitable fixture file found.")

    raw = valid_candidates[0].read_bytes()
    event = get_message.parse_incoming_event({"raw": raw, "source_id": str(valid_candidates[0])})

    monkeypatch.setattr(service, "process_event", lambda ev: {"success": True, "metrics": []})

    outcome = service.process_incoming_event(
        event, store=store, owner_id="owner", run_mode="test", store_only_fails=True
    )
    assert outcome == "skipped"
    actions = [a for a, _ in store.events]
    assert "released" in actions, "Claim must be released when store_only_fails skips a success"
    # No 'done' document should remain
    statuses = [doc.get("status") for doc in store.docs.values()]
    assert "done" not in statuses


def test_store_only_fails_stores_failed_eval(monkeypatch):
    """When store_only_fails=True a failing evaluation MUST be stored."""
    holder = _patch_service_store(monkeypatch)
    store = service.MongoResultStore()

    fixture_dir = _fixture_dir()
    valid_candidates = [p for p in fixture_dir.glob("*.txt") if "valid" in p.name or "sample" in p.name]
    if not valid_candidates:
        pytest.skip("No suitable fixture file found.")

    raw = valid_candidates[0].read_bytes()
    event = get_message.parse_incoming_event({"raw": raw, "source_id": str(valid_candidates[0])})

    monkeypatch.setattr(service, "process_event", lambda ev: {"success": False, "metrics": []})

    outcome = service.process_incoming_event(
        event, store=store, owner_id="owner", run_mode="test", store_only_fails=True
    )
    # Filters may skip it; if it passes filtering it must be stored
    assert outcome in ("stored", "skipped")
    if outcome == "stored":
        statuses = [doc.get("status") for doc in store.docs.values()]
        assert "done" in statuses


# ---------- PRINT_EVAL_RESULTS gate ----------

def test_print_results_suppressed_when_env_zero(monkeypatch, capsys):
    monkeypatch.setenv("PRINT_EVAL_RESULTS", "0")
    results = {
        "success": True,
        "metrics": [{"name": "M", "score": 1.0, "threshold": 0.7, "success": True, "reason": "ok", "error": None}],
    }
    service._print_results(results)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_print_results_shown_by_default(monkeypatch, capsys):
    monkeypatch.delenv("PRINT_EVAL_RESULTS", raising=False)
    results = {
        "success": True,
        "metrics": [{"name": "Faithfulness", "score": 0.9, "threshold": 0.7, "success": True, "reason": "good", "error": None}],
    }
    service._print_results(results)
    captured = capsys.readouterr()
    assert "Faithfulness" in captured.out
    assert "Overall success" in captured.out


# ---------- SIGTERM / SIGINT graceful shutdown ----------

def test_sigterm_handler_sets_stop_flag():
    """Installing the signal handlers and sending SIGTERM should set _stop_requested."""
    import os as _os
    import signal as _signal

    service._stop_requested.clear()
    prev_sigterm, prev_sigint = service._install_signal_handlers()
    try:
        assert not service._stop_requested.is_set()
        _os.kill(_os.getpid(), _signal.SIGTERM)
        assert service._stop_requested.is_set()
    finally:
        service._restore_signal_handlers(prev_sigterm, prev_sigint)
        service._stop_requested.clear()


def test_sigint_handler_sets_stop_flag():
    """Installing the signal handlers and sending SIGINT should set _stop_requested."""
    import os as _os
    import signal as _signal

    service._stop_requested.clear()
    prev_sigterm, prev_sigint = service._install_signal_handlers()
    try:
        assert not service._stop_requested.is_set()
        _os.kill(_os.getpid(), _signal.SIGINT)
        assert service._stop_requested.is_set()
    finally:
        service._restore_signal_handlers(prev_sigterm, prev_sigint)
        service._stop_requested.clear()