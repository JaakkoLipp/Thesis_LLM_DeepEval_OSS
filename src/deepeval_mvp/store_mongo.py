from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient

from deepeval_mvp.models import AIEvent


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _kafka_id(meta: dict[str, Any]) -> str | None:
    kafka = meta.get("kafka") or {}
    topic = kafka.get("topic")
    partition = kafka.get("partition")
    offset = kafka.get("offset")

    if topic is None or partition is None or offset is None:
        return None

    return f"kafka:{topic}:{partition}:{offset}"


def _kafka_id_is_usable(kafka_id: str) -> bool:
    """
    Reject known redaction/placeholder patterns seen in fixture snapshots.
    This keeps production semantics (topic/partition/offset) when real,
    but avoids collisions when fixtures redact to constants.
    """
    parts = kafka_id.split(":")
    if len(parts) != 4:
        return False

    _, topic, partition_s, offset_s = parts

    # topic redacted in fixtures
    if topic.upper() == "REDACTED":
        return False

    try:
        partition = int(partition_s)
        offset = int(offset_s)
    except ValueError:
        return False

    # common fixture placeholder
    if partition == 0 and offset == 0:
        return False

    return True


def _event_id_from_payload(meta: dict[str, Any], user_input: str, output: str) -> str:
    """
    Deterministic event ID derived from JSON payload fields, for fixture mode.
    Uses fields that are typically present (system/session_id/time_stamp/event_type).
    Adds user_input+output into the hash to reduce collision risk if timestamps
    are coarse or redacted.
    """
    system = meta.get("system", "")
    session_id = meta.get("session_id", "")
    time_stamp = meta.get("time_stamp", "")
    event_type = meta.get("event_type", "")

    base = f"{system}|{session_id}|{time_stamp}|{event_type}|{user_input}|{output}"
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()
    return f"evt:{h}"


class MongoResultStore:
    def __init__(self) -> None:
        # Accept both naming conventions (your project uses MONGO_*)
        uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017"
        db_name = os.getenv("MONGO_DB") or os.getenv("MONGODB_DB") or "deepeval_mvp"
        coll_name = (
            os.getenv("MONGO_COLLECTION")
            or os.getenv("MONGODB_COLLECTION")
            or "evaluation_results"
        )

        self._client = MongoClient(uri)

        # Fail fast with a clearer error if auth/host is wrong
        self._client.admin.command("ping")

        self._coll = self._client[db_name][coll_name]

        # Minimal helpful indexes for analysis queries
        self._coll.create_index("meta.system")
        self._coll.create_index("meta.event_type")
        self._coll.create_index("meta.session_id")
        self._coll.create_index("meta.time_stamp")
        self._coll.create_index("evaluation.success")
        self._coll.create_index("stored_at")

    def save(self, event: AIEvent, evaluation: dict[str, Any]) -> str:
        store_full_ctx = _env_bool("STORE_FULL_CONTEXT", False)
        max_chars = int(os.getenv("CONTEXT_STORE_MAX_CHARS", "4000"))

        full_ctx = event.context or ""
        stored_ctx = full_ctx if store_full_ctx else full_ctx[:max_chars]
        truncated = (not store_full_ctx) and (len(full_ctx) > max_chars)

        kid = _kafka_id(event.raw_meta)
        if kid and _kafka_id_is_usable(kid):
            _id = kid
        else:
            _id = _event_id_from_payload(event.raw_meta, event.user_input, event.output)

        doc = {
            "_id": _id,
            "kafka": (event.raw_meta.get("kafka") or {}),
            "meta": {
                "system": event.system,
                "event_type": event.event_type,
                "session_id": event.raw_meta.get("session_id", ""),
                "time_stamp": event.raw_meta.get("time_stamp", ""),
                "log_type": event.raw_meta.get("log_type", ""),
                "tcad": event.raw_meta.get("tcad", ""),
            },
            "payload": {
                "user_input": event.user_input,
                "output": event.output,
                "context": stored_ctx,
                "context_len": len(full_ctx),
                "context_truncated": truncated,
            },
            "evaluation": evaluation,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }

        # Idempotent insert: on reprocessing, keep the original doc unchanged.
        self._coll.update_one({"_id": _id}, {"$setOnInsert": doc}, upsert=True)
        return _id
