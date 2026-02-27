# get_message.py
from __future__ import annotations

import ast
import base64
import json
import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from deepeval_mvp.message_protocol import IncomingMessage  # canonical definition
from deepeval_mvp.models import AIEvent


def _extract_kafka_envelope(raw: bytes) -> dict[str, Any]:
    """
    Parse fields from the KafkaMessage(...) string wrapper in fixture files.
    Best-effort: if a field is missing, it is omitted.
    """
    s = raw.decode("utf-8", errors="replace")
    meta: dict[str, Any] = {}

    m = re.search(r"topic='([^']*)'", s)
    if m:
        meta["topic"] = m.group(1)

    m = re.search(r"partition=(\d+)", s)
    if m:
        meta["partition"] = int(m.group(1))

    m = re.search(r"offset=(\d+)", s)
    if m:
        meta["offset"] = int(m.group(1))

    # key=b'....'  -> store as base64 to keep it JSON-safe
    m = re.search(r"key=(b'[^']*'|b\"[^\"]*\")", s)
    if m:
        try:
            key_bytes = ast.literal_eval(m.group(1))  # yields bytes
            if isinstance(key_bytes, (bytes, bytearray)):
                meta["key_b64"] = base64.b64encode(bytes(key_bytes)).decode("ascii")
        except (ValueError, SyntaxError):
            pass

    return meta


def _event_to_aievent(event: dict[str, Any], kafka_meta: dict[str, Any] | None = None) -> AIEvent:
    meta = {
        "system": event.get("system", ""),
        "event_type": event.get("event_type", ""),
        "session_id": event.get("session_id", ""),
        "time_stamp": event.get("time_stamp", ""),
        "log_type": event.get("log_type", ""),
        "tcad": event.get("tcad", ""),
    }
    if kafka_meta:
        meta["kafka"] = kafka_meta

    user_input = str(event["event_data"]["request"])
    output = str(event["event_data"]["response"]["output"])
    context = str((event.get("retrieval_context") or {}).get("output") or "")

    return AIEvent(
        system=meta["system"],
        event_type=meta["event_type"],
        user_input=user_input,
        context=context,
        output=output,
        raw_meta=meta,
    )



def _extract_json_payload(raw: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        parsed = json.loads(raw.decode("utf-8"))
        if isinstance(parsed, dict):
            return parsed, {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass

    kafka_meta = _extract_kafka_envelope(raw)

    match = re.search(rb"value=b'''(.*?)'''", raw, re.DOTALL)
    if not match:
        raise ValueError("Could not parse incoming message payload.")

    event = json.loads(match.group(1).decode("utf-8"))
    return event, kafka_meta


def parse_incoming_event(message: IncomingMessage) -> AIEvent:
    raw = message.get("raw")
    if not isinstance(raw, (bytes, bytearray)):
        raise TypeError("IncomingMessage.raw must be bytes")

    event, parsed_kafka_meta = _extract_json_payload(bytes(raw))
    kafka_meta = message.get("kafka") or parsed_kafka_meta or None
    return _event_to_aievent(event, kafka_meta=kafka_meta)


def _iter_fixture_messages(poll_seconds: float, max_cycles: int | None) -> Iterator[IncomingMessage]:
    fixture_dir = Path(os.getenv("MESSAGE_FIXTURE_DIR", "tests/fixtures"))
    seen: set[str] = set()
    cycles = 0

    while True:
        if not fixture_dir.exists() or not fixture_dir.is_dir():
            raise FileNotFoundError(f"message source directory not found: {fixture_dir}")

        for fixture_file in sorted(fixture_dir.glob("*.txt")):
            source_id = str(fixture_file.resolve())
            if source_id in seen:
                continue

            seen.add(source_id)
            yield {"raw": fixture_file.read_bytes(), "source_id": source_id}

        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return

        time.sleep(max(0.0, poll_seconds))


def iter_incoming_messages(
    poll_seconds: float = 5.0,
    max_cycles: int | None = None,
) -> Iterator[IncomingMessage]:
    source = os.getenv("MESSAGE_SOURCE", "fixture").strip().lower()
    if source == "fixture":
        yield from _iter_fixture_messages(poll_seconds=poll_seconds, max_cycles=max_cycles)
        return
    raise ValueError(
        f"Unsupported MESSAGE_SOURCE={source!r}. "
        "Production sources should implement the MessageSource protocol "
        "and be injected via run_service(message_source=...)."
    )


def get_message(filepath: str) -> tuple[dict[str, Any], tuple[str, str, str]]:
    with open(filepath, "rb") as f:
        content = f.read()

    aievent = parse_incoming_event({"raw": content, "source_id": filepath})

    meta = dict(aievent.raw_meta)
    payload = (aievent.user_input, aievent.context, aievent.output)
    return meta, payload


def get_event(filepath: str) -> AIEvent:
    with open(filepath, "rb") as f:
        content = f.read()

    return parse_incoming_event({"raw": content, "source_id": filepath})


# ── Protocol-conforming adapter ───────────────────────────────────────────────

class FixtureMessageSource:
    """``MessageSource`` protocol implementation backed by fixture files.

    This is the MVP's default message source.  The production fork should
    replace this with a Kafka-backed implementation that satisfies the same
    ``MessageSource`` protocol.
    """

    def iter_messages(
        self,
        poll_seconds: float = 5.0,
        max_cycles: int | None = None,
    ) -> Iterator[IncomingMessage]:
        yield from iter_incoming_messages(poll_seconds=poll_seconds, max_cycles=max_cycles)

    def parse_event(self, message: IncomingMessage) -> AIEvent:
        return parse_incoming_event(message)
