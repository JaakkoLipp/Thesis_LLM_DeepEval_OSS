from __future__ import annotations

import argparse
from pathlib import Path

from deepeval_mvp.demo import run_demo
from deepeval_mvp.service import run_service


def cmd_demo(fixtures_dir: Path) -> int:
    return run_demo(fixtures_dir)


def cmd_run(fixtures_dir: Path, poll_seconds: float) -> int:
    return run_service(fixtures_dir=fixtures_dir, poll_seconds=poll_seconds)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deepeval-mvp")
    sub = p.add_subparsers(dest="cmd", required=True)

    demo = sub.add_parser("demo", help="Evaluate local fixture files (development only)")
    demo.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/fixtures"),
        help="Directory containing fixture .txt files",
    )

    run = sub.add_parser("run", help="Run as a service (Kafka -> eval -> DB)")
    run.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/fixtures"),
        help="Temporary input source until Kafka is integrated (directory of .txt fixtures)",
    )
    run.add_argument(
        "--poll-seconds",
        type=float,
        default=5.0,
        help="Polling interval for fixture directory in service mode",
    )

    return p


def main() -> int:
    args = build_parser().parse_args()

    if args.cmd == "demo":
        return cmd_demo(args.fixtures)

    if args.cmd == "run":
        return cmd_run(args.fixtures, args.poll_seconds)

    raise SystemExit(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
