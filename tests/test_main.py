from __future__ import annotations

import sys
from pathlib import Path

import deepeval_mvp.main as main


def test_build_parser_defaults_to_service_mode():
    args = main.build_parser().parse_args([])

    assert args.fixtures == Path("tests/fixtures")
    assert args.poll_seconds == 5.0


def test_main_calls_service_with_cli_args(monkeypatch):
    captured = {}

    def fake_cmd_run(fixtures_dir: Path, poll_seconds: float) -> int:
        captured["fixtures_dir"] = fixtures_dir
        captured["poll_seconds"] = poll_seconds
        return 123

    monkeypatch.setattr(main, "cmd_run", fake_cmd_run)
    monkeypatch.setattr(main, "run_preflight", lambda logger: True)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deepeval-mvp",
            "--fixtures",
            "tests/fixtures",
            "--poll-seconds",
            "1.25",
        ],
    )

    rc = main.main()

    assert rc == 123
    assert captured["fixtures_dir"] == Path("tests/fixtures")
    assert captured["poll_seconds"] == 1.25


def test_main_returns_1_when_preflight_fails(monkeypatch):
    monkeypatch.setattr(main, "run_preflight", lambda logger: False)
    monkeypatch.setattr(sys, "argv", ["deepeval-mvp"])

    rc = main.main()

    assert rc == 1
