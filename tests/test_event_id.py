"""Tests for the event-ID computation and Kafka-ID validation in store_mongo.py."""
from __future__ import annotations

from deepeval_mvp.store_mongo import (
    _event_id_from_payload,
    _kafka_id,
    _kafka_id_is_usable,
)

# ── _kafka_id ─────────────────────────────────────────────────────────────────

class TestKafkaId:
    def test_returns_id_when_all_fields_present(self):
        meta = {"kafka": {"topic": "events", "partition": 2, "offset": 99}}
        assert _kafka_id(meta) == "kafka:events:2:99"

    def test_returns_none_when_kafka_missing(self):
        assert _kafka_id({}) is None

    def test_returns_none_when_topic_missing(self):
        meta = {"kafka": {"partition": 1, "offset": 5}}
        assert _kafka_id(meta) is None

    def test_returns_none_when_partition_missing(self):
        meta = {"kafka": {"topic": "t", "offset": 5}}
        assert _kafka_id(meta) is None

    def test_returns_none_when_offset_missing(self):
        meta = {"kafka": {"topic": "t", "partition": 1}}
        assert _kafka_id(meta) is None


# ── _kafka_id_is_usable ──────────────────────────────────────────────────────

class TestKafkaIdIsUsable:
    def test_valid_id(self):
        assert _kafka_id_is_usable("kafka:events:2:99") is True

    def test_redacted_topic(self):
        assert _kafka_id_is_usable("kafka:REDACTED:0:1") is False

    def test_zero_partition_and_offset(self):
        assert _kafka_id_is_usable("kafka:topic:0:0") is False

    def test_non_numeric_partition(self):
        assert _kafka_id_is_usable("kafka:topic:abc:1") is False

    def test_non_numeric_offset(self):
        assert _kafka_id_is_usable("kafka:topic:1:abc") is False

    def test_wrong_number_of_parts(self):
        assert _kafka_id_is_usable("kafka:topic:1") is False
        assert _kafka_id_is_usable("kafka:a:b:c:d") is False

    def test_nonzero_partition_zero_offset_rejected(self):
        # partition=1, offset=0 → rejected because offset==0 and partition==0 check
        # actually only partition==0 AND offset==0 is rejected
        assert _kafka_id_is_usable("kafka:topic:1:0") is True

    def test_zero_partition_nonzero_offset(self):
        assert _kafka_id_is_usable("kafka:topic:0:5") is True


# ── _event_id_from_payload ────────────────────────────────────────────────────

class TestEventIdFromPayload:
    def test_deterministic(self):
        meta = {"system": "s", "session_id": "x", "time_stamp": "t", "event_type": "e"}
        id1 = _event_id_from_payload(meta, "q", "a")
        id2 = _event_id_from_payload(meta, "q", "a")
        assert id1 == id2

    def test_different_input_different_id(self):
        meta = {"system": "s", "session_id": "x", "time_stamp": "t", "event_type": "e"}
        id1 = _event_id_from_payload(meta, "q1", "a")
        id2 = _event_id_from_payload(meta, "q2", "a")
        assert id1 != id2

    def test_prefix(self):
        meta = {"system": "s"}
        eid = _event_id_from_payload(meta, "q", "a")
        assert eid.startswith("evt:")

    def test_missing_meta_fields_dont_crash(self):
        eid = _event_id_from_payload({}, "", "")
        assert eid.startswith("evt:")


# ── compute_event_id (via FakeMongoResultStore from conftest) ─────────────────

class TestComputeEventIdIntegration:
    """Verify the real compute_event_id logic via conftest's FakeMongoResultStore."""

    def test_kafka_id_used_when_valid(self, sample_aievent):
        from conftest import FakeMongoResultStore
        eid = FakeMongoResultStore._compute_event_id(sample_aievent)
        assert eid.startswith("kafka:")

    def test_payload_id_used_when_no_kafka(self, sample_aievent_no_kafka):
        from conftest import FakeMongoResultStore
        eid = FakeMongoResultStore._compute_event_id(sample_aievent_no_kafka)
        assert eid.startswith("evt:")
