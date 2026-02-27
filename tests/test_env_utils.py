"""Tests for the centralised env_utils helpers."""
from __future__ import annotations

import pytest

from deepeval_mvp.env_utils import env_bool, env_csv, env_float, env_int


class TestEnvBool:
    @pytest.mark.parametrize("val", ["1", "true", "True", "TRUE", "yes", "Yes", "y", "Y", "on", "ON"])
    def test_truthy_values(self, monkeypatch, val):
        monkeypatch.setenv("_TEST_BOOL", val)
        assert env_bool("_TEST_BOOL") is True

    @pytest.mark.parametrize("val", ["0", "false", "False", "no", "off", "n", "nope", ""])
    def test_falsy_values(self, monkeypatch, val):
        monkeypatch.setenv("_TEST_BOOL", val)
        assert env_bool("_TEST_BOOL") is False

    def test_missing_returns_default_false(self, monkeypatch):
        monkeypatch.delenv("_TEST_BOOL", raising=False)
        assert env_bool("_TEST_BOOL") is False

    def test_missing_returns_custom_default(self, monkeypatch):
        monkeypatch.delenv("_TEST_BOOL", raising=False)
        assert env_bool("_TEST_BOOL", default=True) is True


class TestEnvFloat:
    def test_parses_float(self, monkeypatch):
        monkeypatch.setenv("_TEST_FLOAT", "3.14")
        assert env_float("_TEST_FLOAT", 0.0) == pytest.approx(3.14)

    def test_missing_returns_default(self, monkeypatch):
        monkeypatch.delenv("_TEST_FLOAT", raising=False)
        assert env_float("_TEST_FLOAT", 2.5) == pytest.approx(2.5)

    def test_whitespace_only_returns_default(self, monkeypatch):
        monkeypatch.setenv("_TEST_FLOAT", "   ")
        assert env_float("_TEST_FLOAT", 9.9) == pytest.approx(9.9)


class TestEnvInt:
    def test_parses_int(self, monkeypatch):
        monkeypatch.setenv("_TEST_INT", "42")
        assert env_int("_TEST_INT", 0) == 42

    def test_missing_returns_default(self, monkeypatch):
        monkeypatch.delenv("_TEST_INT", raising=False)
        assert env_int("_TEST_INT", 7) == 7

    def test_whitespace_only_returns_default(self, monkeypatch):
        monkeypatch.setenv("_TEST_INT", "  ")
        assert env_int("_TEST_INT", 99) == 99


class TestEnvCsv:
    def test_splits_and_strips(self, monkeypatch):
        monkeypatch.setenv("_TEST_CSV", " a , b , c ")
        assert env_csv("_TEST_CSV") == ["a", "b", "c"]

    def test_filters_empty_segments(self, monkeypatch):
        monkeypatch.setenv("_TEST_CSV", "a,,b,")
        assert env_csv("_TEST_CSV") == ["a", "b"]

    def test_missing_returns_default_parsed(self, monkeypatch):
        monkeypatch.delenv("_TEST_CSV", raising=False)
        assert env_csv("_TEST_CSV", "x,y") == ["x", "y"]

    def test_missing_no_default_returns_empty(self, monkeypatch):
        monkeypatch.delenv("_TEST_CSV", raising=False)
        assert env_csv("_TEST_CSV") == []
