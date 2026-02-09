# get_message.py
from __future__ import annotations

import json
import re
from typing import Any

from deepeval_mvp.models import AIEvent

def _event_to_aievent(event: dict[str, Any]) -> AIEvent:
    meta = {
        "system": event.get("system", ""),
        "event_type": event.get("event_type", ""),
        "session_id": event.get("session_id", ""),
        "time_stamp": event.get("time_stamp", ""),
    }

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

    match = re.search(rb"value=b'''(.*?)'''", content, re.DOTALL)
    if not match:
        raise ValueError("Could not extract JSON payload from file (expected value=b'''...''').")

    event = json.loads(match.group(1).decode("utf-8"))
    aievent = _event_to_aievent(event)

    meta = dict(aievent.raw_meta)
    payload = (aievent.user_input, aievent.context, aievent.output)
    return meta, payload


def get_event(filepath: str) -> AIEvent:
    with open(filepath, "rb") as f:
        content = f.read()

    match = re.search(rb"value=b'''(.*?)'''", content, re.DOTALL)
    if not match:
        raise ValueError("Could not extract JSON payload from file (expected value=b'''...''').")

    event = json.loads(match.group(1).decode("utf-8"))
    return _event_to_aievent(event)
