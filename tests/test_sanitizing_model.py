"""Tests for the _SanitizingOllamaModel helper methods (now module-level).

These are pure functions that don't require deepeval or an LLM connection,
so they run fast and deterministically.
"""
from __future__ import annotations

import pytest

from deepeval_mvp.eval import _SanitizingOllamaModel


# ── _clean ────────────────────────────────────────────────────────────────────

class TestClean:
    def test_plain_json_unchanged(self):
        raw = '{"score": 0.8, "reason": "ok"}'
        assert _SanitizingOllamaModel._clean(raw) == raw

    def test_strips_json_code_fence(self):
        raw = '```json\n{"score": 0.8}\n```'
        assert _SanitizingOllamaModel._clean(raw) == '{"score": 0.8}'

    def test_strips_bare_code_fence(self):
        raw = '```\n{"score": 0.8}\n```'
        assert _SanitizingOllamaModel._clean(raw) == '{"score": 0.8}'

    def test_replaces_nbsp(self):
        raw = '{"score":\xa00.8}'
        assert "\xa0" not in _SanitizingOllamaModel._clean(raw)
        assert _SanitizingOllamaModel._clean(raw) == '{"score": 0.8}'

    def test_strips_whitespace(self):
        raw = '   {"score": 0.8}   '
        assert _SanitizingOllamaModel._clean(raw) == '{"score": 0.8}'

    def test_fence_with_extra_whitespace(self):
        raw = '```json  \n  {"a": 1}  \n  ```'
        assert _SanitizingOllamaModel._clean(raw) == '{"a": 1}'

    def test_empty_string(self):
        assert _SanitizingOllamaModel._clean("") == ""

    def test_fence_with_multiline_json(self):
        raw = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
        cleaned = _SanitizingOllamaModel._clean(raw)
        assert cleaned.startswith("{")
        assert cleaned.endswith("}")


# ── _get_system_prompt ────────────────────────────────────────────────────────

class TestGetSystemPrompt:
    def test_returns_none_when_nothing_set(self, monkeypatch):
        monkeypatch.delenv("JUDGE_SYSTEM_PROMPT", raising=False)
        monkeypatch.delenv("JUDGE_SYSTEM_PROMPT_FILE", raising=False)
        assert _SanitizingOllamaModel._get_system_prompt() is None

    def test_returns_inline_prompt(self, monkeypatch):
        monkeypatch.delenv("JUDGE_SYSTEM_PROMPT_FILE", raising=False)
        monkeypatch.setenv("JUDGE_SYSTEM_PROMPT", "Be concise.")
        assert _SanitizingOllamaModel._get_system_prompt() == "Be concise."

    def test_returns_none_for_empty_inline(self, monkeypatch):
        monkeypatch.delenv("JUDGE_SYSTEM_PROMPT_FILE", raising=False)
        monkeypatch.setenv("JUDGE_SYSTEM_PROMPT", "   ")
        assert _SanitizingOllamaModel._get_system_prompt() is None

    def test_file_takes_precedence_over_inline(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "system.txt"
        prompt_file.write_text("From file.", encoding="utf-8")

        monkeypatch.setenv("JUDGE_SYSTEM_PROMPT_FILE", str(prompt_file))
        monkeypatch.setenv("JUDGE_SYSTEM_PROMPT", "From inline.")
        assert _SanitizingOllamaModel._get_system_prompt() == "From file."

    def test_empty_file_falls_through(self, monkeypatch, tmp_path):
        """An existing but empty file should return None, not empty string."""
        prompt_file = tmp_path / "empty.txt"
        prompt_file.write_text("   ", encoding="utf-8")

        monkeypatch.setenv("JUDGE_SYSTEM_PROMPT_FILE", str(prompt_file))
        monkeypatch.setenv("JUDGE_SYSTEM_PROMPT", "From inline.")
        # File exists but is whitespace-only → returns None
        assert _SanitizingOllamaModel._get_system_prompt() is None
