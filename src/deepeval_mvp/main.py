from __future__ import annotations

import argparse
from pathlib import Path

from deepeval_mvp.logging_utils import configure_logging, get_logger
from deepeval_mvp.preflight import run_preflight
from deepeval_mvp.service import run_service
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH)
configure_logging()

def cmd_run(fixtures_dir: Path, poll_seconds: float) -> int:
    return run_service(fixtures_dir=fixtures_dir, poll_seconds=poll_seconds)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deepeval-mvp")
    p.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/fixtures"),
        help="Temporary input source until Kafka is integrated (directory of .txt fixtures)",
    )
    p.add_argument(
        "--poll-seconds",
        type=float,
        default=5.0,
        help="Polling interval for fixture directory in service mode",
    )

    return p


def main() -> int:
    args = build_parser().parse_args()
    logger = get_logger("startup")
    if not run_preflight(logger):
        return 1
    return cmd_run(args.fixtures, args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
