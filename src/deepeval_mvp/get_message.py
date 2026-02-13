# get_message.py
from __future__ import annotations

import json
import re
from typing import Any
import ast
import base64

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
        except Exception:
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



def get_message(filepath: str) -> tuple[dict[str, Any], tuple[str, str, str]]:
    with open(filepath, "rb") as f:
        content = f.read()

    kafka_meta = _extract_kafka_envelope(content)

    match = re.search(rb"value=b'''(.*?)'''", content, re.DOTALL)
    if not match:
        raise ValueError("Could not extract JSON payload from file (expected value=b'''...''').")

    event = json.loads(match.group(1).decode("utf-8"))
    aievent = _event_to_aievent(event, kafka_meta=kafka_meta)

    meta = dict(aievent.raw_meta)
    payload = (aievent.user_input, aievent.context, aievent.output)
    return meta, payload


def get_event(filepath: str) -> AIEvent:
    with open(filepath, "rb") as f:
        content = f.read()

    kafka_meta = _extract_kafka_envelope(content)

    match = re.search(rb"value=b'''(.*?)'''", content, re.DOTALL)
    if not match:
        raise ValueError("Could not extract JSON payload from file (expected value=b'''...''').")

    event = json.loads(match.group(1).decode("utf-8"))
    return _event_to_aievent(event, kafka_meta=kafka_meta)
