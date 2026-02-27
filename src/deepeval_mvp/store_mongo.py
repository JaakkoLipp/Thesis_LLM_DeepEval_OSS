from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient

from deepeval_mvp.env_utils import env_bool, env_int
from deepeval_mvp.models import AIEvent


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
        self._coll = self._client[db_name][coll_name]

        # Ensure helpful indexes exist.  create_index() is a no-op when the
        # index already exists, but we guard with a flag to avoid issuing
        # eight round-trips on every service restart in busy environments.
        if env_bool("MONGO_ENSURE_INDEXES", True):
            self._coll.create_index("meta.system")
            self._coll.create_index("meta.event_type")
            self._coll.create_index("meta.session_id")
            self._coll.create_index("meta.time_stamp")
            self._coll.create_index("evaluation.success")
            self._coll.create_index("stored_at")
            self._coll.create_index("status")
            self._coll.create_index("owner_id")

        # Payload config read once at construction — not on every event.
        self._store_full_context: bool = env_bool("STORE_FULL_CONTEXT", False)
        self._context_store_max_chars: int = env_int("CONTEXT_STORE_MAX_CHARS", 4000)

    def compute_event_id(self, event: AIEvent) -> str:
        kid = _kafka_id(event.raw_meta)
        if kid and _kafka_id_is_usable(kid):
            return kid
        return _event_id_from_payload(event.raw_meta, event.user_input, event.output)

    def exists(self, event_id: str) -> bool:
        return self._coll.count_documents({"_id": event_id}, limit=1) > 0

    def _build_base_doc(self, event: AIEvent) -> dict[str, Any]:
        return {
            "kafka": (event.raw_meta.get("kafka") or {}),
            "meta": {
                "system": event.system,
                "event_type": event.event_type,
                "session_id": event.raw_meta.get("session_id", ""),
                "time_stamp": event.raw_meta.get("time_stamp", ""),
                "log_type": event.raw_meta.get("log_type", ""),
                "tcad": event.raw_meta.get("tcad", ""),
            },
            "payload": self._build_payload(event),
        }

    def claim_event(self, event: AIEvent, owner_id: str) -> tuple[str, bool]:
        event_id = self.compute_event_id(event)
        now = datetime.now(timezone.utc).isoformat()
        base_doc = self._build_base_doc(event)

        claim_doc = {
            "_id": event_id,
            **base_doc,
            "status": "processing",
            "owner_id": owner_id,
            "started_at": now,
            "claimed_at": now,
            "last_updated_at": now,
            "attempts": 1,
        }

        result = self._coll.update_one({"_id": event_id}, {"$setOnInsert": claim_doc}, upsert=True)
        return event_id, bool(result.upserted_id)

    def release_claim(self, event_id: str) -> None:
        """Delete a previously claimed document so no trace remains in MongoDB."""
        self._coll.delete_one({"_id": event_id})

    def mark_done(self, event_id: str, event: AIEvent, evaluation: dict[str, Any]) -> None:
        base_doc = self._build_base_doc(event)
        base_doc_without_payload = {
            "kafka": base_doc["kafka"],
            "meta": base_doc["meta"],
        }
        payload = self._build_payload(event)
        now = datetime.now(timezone.utc).isoformat()
        eval_version = os.getenv("EVAL_VERSION", "unknown")
        self._coll.update_one(
            {"_id": event_id},
            {
                "$setOnInsert": {
                    "_id": event_id,
                    **base_doc_without_payload,
                    "started_at": now,
                },
                "$set": {
                    "status": "done",
                    "payload": payload,
                    "evaluation": evaluation,
                    "eval_version": eval_version,
                    "finished_at": now,
                    "stored_at": now,
                    "last_updated_at": now,
                }
            },
            upsert=True,
        )

    def mark_skipped(self, event_id: str, event: AIEvent) -> None:
        base_doc = self._build_base_doc(event)
        base_doc_without_payload = {
            "kafka": base_doc["kafka"],
            "meta": base_doc["meta"],
        }
        payload = self._build_payload(event)
        now = datetime.now(timezone.utc).isoformat()
        self._coll.update_one(
            {"_id": event_id},
            {
                "$setOnInsert": {
                    "_id": event_id,
                    **base_doc_without_payload,
                    "started_at": now,
                },
                "$set": {
                    "status": "skipped",
                    "payload": payload,
                    "finished_at": now,
                    "stored_at": now,
                    "last_updated_at": now,
                }
            },
            upsert=True,
        )

    def mark_error(
        self,
        event_id: str,
        error_type: str,
        error_message: str,
        *,
        event: AIEvent | None = None,
        traceback_text: str | None = None,
    ) -> None:
        """Persist an error record for event_id.

        Args:
            event_id:       Document _id.
            error_type:     Exception class name (e.g. ``ValueError``).
            error_message:  Human-readable error description.
            event:          Optional AIEvent; when provided, base metadata is persisted.
            traceback_text: Optional full traceback string (truncated to ERROR_TRACEBACK_MAX_CHARS).
        """

        now = datetime.now(timezone.utc).isoformat()
        max_chars = int(os.getenv("ERROR_TRACEBACK_MAX_CHARS", "2000"))
        traceback_truncated = (traceback_text or "")[:max_chars]

        set_on_insert: dict[str, Any] = {
            "_id": event_id,
            "started_at": now,
        }
        if isinstance(event, AIEvent):
            set_on_insert.update(self._build_base_doc(event))

        error_doc: dict[str, Any] = {
            "type": error_type,
            "message": error_message,
        }
        if traceback_text is not None:
            error_doc["traceback_truncated"] = traceback_truncated

        self._coll.update_one(
            {"_id": event_id},
            {
                "$setOnInsert": set_on_insert,
                "$set": {
                    "status": "error",
                    "finished_at": now,
                    "stored_at": now,
                    "error": error_doc,
                    "last_updated_at": now,
                }
            },
            upsert=True,
        )

    def get_owner(self, event_id: str) -> str | None:
        doc = self._coll.find_one({"_id": event_id}, {"owner_id": 1})
        if not doc:
            return None
        return doc.get("owner_id")

    def _build_payload(self, event: AIEvent) -> dict[str, Any]:
        """Build the payload sub-document.  Config is read from instance vars
        set at construction time, not from env on every call.
        """
        full_ctx = event.context or ""
        if self._store_full_context:
            stored_ctx = full_ctx
            truncated = False
        else:
            stored_ctx = full_ctx[: self._context_store_max_chars]
            truncated = len(full_ctx) > self._context_store_max_chars

        return {
            "user_input": event.user_input,
            "output": event.output,
            "context": stored_ctx,
            "context_len": len(full_ctx),
            "context_truncated": truncated,
        }
