from __future__ import annotations

import importlib
import sys
import types
from typing import Any

import pytest


class FakeLLMTestCase:
    # Accept the same call shape as production: LLMTestCase(input=..., actual_output=..., retrieval_context=...)
    def __init__(self, **kwargs: Any):
        # store exactly what your eval_function passes
        self.input = kwargs.get("input")
        self.actual_output = kwargs.get("actual_output")
        self.retrieval_context = kwargs.get("retrieval_context", [])


class FakeMetric:
    def __init__(
        self,
        name: str,
        success: bool,
        score: float = 0.8,
        threshold: float = 0.7,
        reason: str = "ok",
        error: str | None = None,
    ):
        self.name = name
        self._success = success
        self.score = score
        self.threshold = threshold
        self.reason = reason
        self.error = error
        self.seen_test_case = None

    def measure(self, test_case: Any) -> None:
        self.seen_test_case = test_case

    def is_successful(self) -> bool:
        return self._success


def _install_fake_deepeval_modules(monkeypatch):
    fake_test_case_mod: Any = types.ModuleType("deepeval.test_case")
    fake_test_case_mod.LLMTestCase = FakeLLMTestCase

    class FakeParams:
        INPUT = "INPUT"
        ACTUAL_OUTPUT = "ACTUAL_OUTPUT"
        CONTEXT = "CONTEXT"

    fake_test_case_mod.LLMTestCaseParams = FakeParams

    monkeypatch.setitem(sys.modules, "deepeval", types.ModuleType("deepeval"))
    monkeypatch.setitem(sys.modules, "deepeval.test_case", fake_test_case_mod)


@pytest.fixture
def eval_module(monkeypatch: pytest.MonkeyPatch):
    _install_fake_deepeval_modules(monkeypatch)

    # ensure fresh import
    sys.modules.pop("deepeval_mvp.eval", None)

    import deepeval_mvp.eval as m
    importlib.reload(m)
    return m


def test_eval_function_truncates_context_and_aggregates_success(monkeypatch: pytest.MonkeyPatch, eval_module):
    monkeypatch.setenv("MAX_CONTEXT_CHARS", "10")

    # In unit tests we stub deepeval modules; avoid dependency presence checks.
    monkeypatch.setattr(eval_module, "_require_deepeval", lambda: None)

    fake_judge = object()
    monkeypatch.setattr(eval_module, "_build_judge", lambda: fake_judge)

    m1 = FakeMetric(name="Faithfulness", success=True)
    m2 = FakeMetric(name="AnswerRelevancy", success=False, reason="not relevant")

    def fake_build_metrics(judge: Any):
        assert judge is fake_judge
        return [m1, m2]

    monkeypatch.setattr(eval_module, "_build_metrics", fake_build_metrics)

    user_input = "What is X?"
    context = "0123456789ABCDEFGHIJ"
    output = "Answer"

    res = eval_module.eval_function(user_input, context, output)

    assert res["success"] is False
    assert isinstance(res["metrics"], list)
    assert len(res["metrics"]) == 2

    assert m1.seen_test_case is not None
    assert m1.seen_test_case.retrieval_context == ["0123456789"]
    assert m1.seen_test_case.input == user_input
    assert m1.seen_test_case.actual_output == output

    names = [x["name"] for x in res["metrics"]]
    assert "Faithfulness" in names
    assert "AnswerRelevancy" in names

    ar = next(x for x in res["metrics"] if x["name"] == "AnswerRelevancy")
    assert ar["success"] is False
    assert ar["reason"] == "not relevant"


def test_eval_function_all_success(monkeypatch, eval_module):
    monkeypatch.setattr(eval_module, "_require_deepeval", lambda: None)
    monkeypatch.setattr(eval_module, "_build_judge", lambda: object())
    monkeypatch.setattr(eval_module, "_build_metrics", lambda judge: [FakeMetric("M1", True), FakeMetric("M2", True)])

    res = eval_module.eval_function("q", "ctx", "out")
    assert res["success"] is True


def test_eval_function_no_metrics_is_not_success(monkeypatch, eval_module):
    monkeypatch.setattr(eval_module, "_require_deepeval", lambda: None)
    monkeypatch.setattr(eval_module, "_build_judge", lambda: object())
    monkeypatch.setattr(eval_module, "_build_metrics", lambda judge: [])

    res = eval_module.eval_function("q", "ctx", "out")
    assert res["metrics"] == []
    assert res["success"] is False
