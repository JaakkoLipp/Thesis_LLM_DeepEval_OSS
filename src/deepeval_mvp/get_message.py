import re
import json

def get_message(filepath: str) -> dict:
    """Extracts a JSON payload from a file at the given filepath."""
    with open(filepath, "rb") as f:
        content = f.read()

    match = re.search(rb"value=b'''(.*?)'''", content, re.DOTALL)
    if not match:
        raise ValueError("Could not extract JSON payload")

    json_bytes = match.group(1)
    return json.loads(json_bytes.decode("utf-8"))
