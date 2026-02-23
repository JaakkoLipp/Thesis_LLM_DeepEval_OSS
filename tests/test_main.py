from __future__ import annotations

import sys

import deepeval_mvp.main as main


def test_build_parser_defaults_to_service_mode():
    args = main.build_parser().parse_args([])

    assert args.poll_seconds == 5.0
    assert args.max_cycles is None


def test_main_calls_service_with_cli_args(monkeypatch):
    captured = {}

    def fake_cmd_run(poll_seconds: float, max_cycles: int | None) -> int:
        captured["poll_seconds"] = poll_seconds
        captured["max_cycles"] = max_cycles
        return 123

    monkeypatch.setattr(main, "cmd_run", fake_cmd_run)
    monkeypatch.setattr(main, "run_preflight", lambda logger: True)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deepeval-mvp",
            "--poll-seconds",
            "1.25",
            "--max-cycles",
            "2",
        ],
    )

    rc = main.main()

    assert rc == 123
    assert captured["poll_seconds"] == 1.25
    assert captured["max_cycles"] == 2


def test_main_returns_1_when_preflight_fails(monkeypatch):
    monkeypatch.setattr(main, "run_preflight", lambda logger: False)
    monkeypatch.setattr(sys, "argv", ["deepeval-mvp"])

    rc = main.main()

    assert rc == 1
