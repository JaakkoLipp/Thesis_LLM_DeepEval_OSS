from __future__ import annotations

from deepeval_mvp.models import AIEvent
from deepeval_mvp.store_mongo import MongoResultStore


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


class _FakeCollection:
    def __init__(self) -> None:
        self.calls = []

    def update_one(self, filt, update, upsert=False):
        self.calls.append((filt, update, upsert))


def _build_store_with_fake_collection() -> tuple[MongoResultStore, _FakeCollection]:
    coll = _FakeCollection()
    store = MongoResultStore.__new__(MongoResultStore)
    store._coll = coll
    # Payload config normally set in __init__; must be present for _build_payload calls.
    store._store_full_context = False
    store._context_store_max_chars = 4000
    return store, coll


def test_mark_done_does_not_conflict_update_paths():
    store, coll = _build_store_with_fake_collection()

    store.mark_done("evt-1", _sample_event(), {"metrics": [], "success": True})

    _, update, _ = coll.calls[-1]
    assert "payload" not in update["$setOnInsert"]
    assert "payload" in update["$set"]


def test_payload_context_truncated(monkeypatch):
    store, _ = _build_store_with_fake_collection()
    store._store_full_context = False
    store._context_store_max_chars = 5

    event = AIEvent(
        system="s", event_type="e",
        user_input="q", context="0123456789", output="o",
        raw_meta={},
    )
    payload = store._build_payload(event)
    assert payload["context"] == "01234"
    assert payload["context_truncated"] is True
    assert payload["context_len"] == 10


def test_payload_context_full_when_flag_set():
    store, _ = _build_store_with_fake_collection()
    store._store_full_context = True
    store._context_store_max_chars = 5  # max_chars is irrelevant when full

    event = AIEvent(
        system="s", event_type="e",
        user_input="q", context="0123456789", output="o",
        raw_meta={},
    )
    payload = store._build_payload(event)
    assert payload["context"] == "0123456789"
    assert payload["context_truncated"] is False
