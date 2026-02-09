from __future__ import annotations

from pathlib import Path

from deepeval_mvp.get_message import get_event
from deepeval_mvp.pipeline import process_event

def run_demo(fixtures_dir: Path) -> int:
    if not fixtures_dir.exists():
        raise SystemExit(f"Fixtures dir not found: {fixtures_dir}")

    files = sorted(fixtures_dir.glob("*.txt"))
    if not files:
        print(f"No fixtures found in: {fixtures_dir}")
        return 0

    for f in files:
        event = get_event(str(f))

        results = process_event(event)
        if results is None:
            print(f"Skipping {f.name} ...")
        else:
            print(f"Running {f.name} ...")
            _print_results(results)

    return 0


def _print_results(results: dict) -> None:
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
