from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

from deepeval_mvp.get_message import get_event
from deepeval_mvp.pipeline import process_event
from deepeval_mvp.store_mongo import MongoResultStore


def process_fixture_file(
    fixture_path: Path,
    store: Any,
    run_mode: str = "service",
) -> Literal["stored", "skipped", "error"]:
    started = time.monotonic()

    try:
        event = get_event(str(fixture_path))
        result = process_event(event)

        if result is None:
            print(f"[{run_mode}] skipped {fixture_path.name}")
            return "skipped"

        _print_results(result)
        event_id = store.save(event, result)
        duration_ms = int((time.monotonic() - started) * 1000)
        print(f"[{run_mode}] stored {fixture_path.name} as {event_id} in {duration_ms}ms")
        return "stored"
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        print(
            f"[{run_mode}] error {fixture_path.name} ({type(exc).__name__}) after {duration_ms}ms: {exc}"
        )
        return "error"


def _print_results(results: dict[str, Any]) -> None:
    print("\n=== Evaluation Results ===")
    for metric in results["metrics"]:
        print(f"\n[{metric['name']}]")
        print(f"  score      : {metric['score']}")
        print(f"  threshold  : {metric['threshold']}")
        print(f"  success    : {metric['success']}")
        print(f"  reason     : {metric['reason']}")
        if metric.get("error"):
            print(f"  error      : {metric['error']}")
    print("\nOverall success:", results["success"])


def run_service(fixtures_dir: Path, poll_seconds: float = 5.0, max_cycles: int | None = None) -> int:
    """
    Temporary service mode: poll a directory for new fixture files and process them once.
    This simulates a consumer loop until Kafka integration exists.
    """
    seen: set[str] = set()
    store = MongoResultStore()
    cycles = 0

    while True:
        if not fixtures_dir.exists():
            print(f"[service] fixtures dir not found: {fixtures_dir}")
            return 1

        for f in sorted(fixtures_dir.glob("*.txt")):
            key = str(f.resolve())
            if key in seen:
                continue

            seen.add(key)
            process_fixture_file(f, store, run_mode="service")

        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return 0

        time.sleep(max(poll_seconds, 0.0))
