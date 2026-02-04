import json
import re
from typing import Any


def get_message(filepath: str) -> tuple[dict[str, Any], tuple[str, str, str]]:
    """
    Parse a Kafka-style payload file and return:
      meta:   {"system": ..., "event_type": ..., "session_id": ..., "time_stamp": ...}
      payload:(user_input, retrieval_context, output)
    """
    with open(filepath, "rb") as f:
        content = f.read()

    match = re.search(rb"value=b'''(.*?)'''", content, re.DOTALL)
    if not match:
        raise ValueError("Could not extract JSON payload from file (expected value=b'''...''').")

    event = json.loads(match.group(1).decode("utf-8"))

    meta = {
        "system": event.get("system", ""),
        "event_type": event.get("event_type", ""),
        "session_id": event.get("session_id", ""),
        "time_stamp": event.get("time_stamp", ""),
    }

    user_input = event["event_data"]["request"]
    output = event["event_data"]["response"]["output"]
    context = (event.get("retrieval_context") or {}).get("output") or ""

    payload = (str(user_input), str(context), str(output))
    return meta, payload
