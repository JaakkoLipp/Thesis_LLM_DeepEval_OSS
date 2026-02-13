from __future__ import annotations

import time
from pathlib import Path

from deepeval_mvp.get_message import get_event
from deepeval_mvp.pipeline import process_event
from deepeval_mvp.store_mongo import MongoResultStore


def run_service(fixtures_dir: Path, poll_seconds: float = 5.0) -> int:
    """
    Temporary service mode: poll a directory for new fixture files and process them once.
    This simulates a consumer loop until Kafka integration exists.
    """
    seen: set[str] = set()
    store = MongoResultStore()

    while True:
        if not fixtures_dir.exists():
            raise SystemExit(f"Fixtures dir not found: {fixtures_dir}")

        for f in sorted(fixtures_dir.glob("*.txt")):
            key = str(f.resolve())
            if key in seen:
                continue

            seen.add(key)
            event = get_event(str(f))
            res = process_event(event)

            if res is not None:
                store_id = store.save(event, res)
                print(f"[service] evaluated {f.name} -> {store_id}")
            else:
                print(f"[service] skipped {f.name}")

        time.sleep(poll_seconds)
