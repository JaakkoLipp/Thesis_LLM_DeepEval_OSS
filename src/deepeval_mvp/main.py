from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from deepeval_mvp.logging_utils import configure_logging, get_logger
from deepeval_mvp.preflight import run_preflight
from deepeval_mvp.service import run_service

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deepeval-mvp")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-cycles", type=int, default=None)
    return parser


def cmd_run(poll_seconds: float, max_cycles: int | None) -> int:
    return run_service(poll_seconds=poll_seconds, max_cycles=max_cycles)

def main() -> int:
    load_dotenv(dotenv_path=ENV_PATH)
    configure_logging()

    logger = get_logger("startup")
    if not run_preflight(logger):
        return 1

    args = build_parser().parse_args()
    return cmd_run(poll_seconds=args.poll_seconds, max_cycles=args.max_cycles)

if __name__ == "__main__":
    raise SystemExit(main())
