"""Tests for _run_metric retry logic in eval.py."""
from __future__ import annotations

import importlib
import sys
import types
from typing import Any

import pytest


class _FakeLLMTestCase:
    def __init__(self, **kwargs: Any):
        self.input = kwargs.get("input")
        self.actual_output = kwargs.get("actual_output")
        self.retrieval_context = kwargs.get("retrieval_context", [])


class _SucceedingMetric:
    """Metric that always succeeds."""
    def __init__(self):
        self.score = 0.9
        self.threshold = 0.7
        self.reason = "ok"
        self.error = None
        self.name = "AlwaysPass"

    def measure(self, test_case: Any) -> None:
        pass

    def is_successful(self) -> bool:
        return True


class _FailOnceMetric:
    """Metric that raises on the first call, then succeeds."""
    def __init__(self):
        self.score = 0.9
        self.threshold = 0.7
        self.reason = "recovered"
        self.error = None
        self.name = "FailOnce"
        self._attempts = 0

    def measure(self, test_case: Any) -> None:
        self._attempts += 1
        if self._attempts == 1:
            raise RuntimeError("transient failure")

    def is_successful(self) -> bool:
        return True


class _AlwaysFailMetric:
    """Metric that always raises."""
    def __init__(self):
        self.score = None
        self.threshold = 0.7
        self.reason = None
        self.error = None
        self.name = "AlwaysFail"

    def measure(self, test_case: Any) -> None:
        raise RuntimeError("permanent failure")

    def is_successful(self) -> bool:
        return False


def _install_fake_deepeval(monkeypatch):
    fake_tc = types.ModuleType("deepeval.test_case")
    fake_tc.LLMTestCase = _FakeLLMTestCase

    class FakeParams:
        INPUT = "INPUT"
        ACTUAL_OUTPUT = "ACTUAL_OUTPUT"
        CONTEXT = "CONTEXT"

    fake_tc.LLMTestCaseParams = FakeParams

    monkeypatch.setitem(sys.modules, "deepeval", types.ModuleType("deepeval"))
    monkeypatch.setitem(sys.modules, "deepeval.test_case", fake_tc)


@pytest.fixture
def eval_mod(monkeypatch):
    _install_fake_deepeval(monkeypatch)
    sys.modules.pop("deepeval_mvp.eval", None)
    import deepeval_mvp.eval as m
    importlib.reload(m)
    return m


class TestRunMetricRetry:
    def test_no_retries_success(self, monkeypatch, eval_mod):
        monkeypatch.setenv("EVAL_RETRIES", "0")
        metric = _SucceedingMetric()
        tc = _FakeLLMTestCase(input="q", actual_output="a")

        result = eval_mod._run_metric(metric, tc, name_override=getattr(metric, "name", None))
        assert result["success"] is True
        assert result["name"] == "AlwaysPass"  # uses metric.name attribute

    def test_no_retries_raises(self, monkeypatch, eval_mod):
        monkeypatch.setenv("EVAL_RETRIES", "0")
        metric = _AlwaysFailMetric()
        tc = _FakeLLMTestCase(input="q", actual_output="a")

        with pytest.raises(RuntimeError, match="permanent failure"):
            eval_mod._run_metric(metric, tc)

    def test_one_retry_recovers(self, monkeypatch, eval_mod):
        monkeypatch.setenv("EVAL_RETRIES", "1")
        monkeypatch.setenv("EVAL_RETRY_BACKOFF_MS", "0")  # no sleep in tests
        metric = _FailOnceMetric()
        tc = _FakeLLMTestCase(input="q", actual_output="a")

        result = eval_mod._run_metric(metric, tc, name_override=getattr(metric, "name", None))
        assert result["success"] is True
        assert result["name"] == "FailOnce"  # uses metric.name attribute
        assert metric._attempts == 2

    def test_retries_exhausted_raises_last(self, monkeypatch, eval_mod):
        monkeypatch.setenv("EVAL_RETRIES", "2")
        monkeypatch.setenv("EVAL_RETRY_BACKOFF_MS", "0")
        metric = _AlwaysFailMetric()
        tc = _FakeLLMTestCase(input="q", actual_output="a")

        with pytest.raises(RuntimeError, match="permanent failure"):
            eval_mod._run_metric(metric, tc)



    def test_negative_retries_are_clamped_to_zero(self, monkeypatch, eval_mod):
        monkeypatch.setenv("EVAL_RETRIES", "-3")
        metric = _FailOnceMetric()
        tc = _FakeLLMTestCase(input="q", actual_output="a")

        with pytest.raises(RuntimeError, match="transient failure"):
            eval_mod._run_metric(metric, tc)
        assert metric._attempts == 1

    def test_negative_backoff_is_clamped_to_zero(self, monkeypatch, eval_mod):
        monkeypatch.setenv("EVAL_RETRIES", "1")
        monkeypatch.setenv("EVAL_RETRY_BACKOFF_MS", "-10")
        metric = _FailOnceMetric()
        tc = _FakeLLMTestCase(input="q", actual_output="a")

        sleeps: list[float] = []
        monkeypatch.setattr(eval_mod.time, "sleep", lambda seconds: sleeps.append(seconds))

        result = eval_mod._run_metric(metric, tc, name_override=getattr(metric, "name", None))
        assert result["success"] is True
        assert sleeps == [0.0]


class TestEvalVersion:
    def test_eval_version_stamped_in_result(self, monkeypatch, eval_mod):
        monkeypatch.setenv("EVAL_VERSION", "v0.2-test")
        monkeypatch.setattr(eval_mod, "_require_deepeval", lambda: None)
        monkeypatch.setattr(eval_mod, "_build_judge", lambda: object())
        monkeypatch.setattr(eval_mod, "_build_metrics", lambda judge: [_SucceedingMetric()])

        result = eval_mod.eval_function("q", "ctx", "out")
        assert result["eval_version"] == "v0.2-test"

    def test_eval_version_defaults_to_unknown(self, monkeypatch, eval_mod):
        monkeypatch.delenv("EVAL_VERSION", raising=False)
        monkeypatch.setattr(eval_mod, "_require_deepeval", lambda: None)
        monkeypatch.setattr(eval_mod, "_build_judge", lambda: object())
        monkeypatch.setattr(eval_mod, "_build_metrics", lambda judge: [_SucceedingMetric()])

        result = eval_mod.eval_function("q", "ctx", "out")
        assert result["eval_version"] == "unknown"
