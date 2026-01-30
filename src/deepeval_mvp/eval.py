from __future__ import annotations

from typing import Any

from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)
from deepeval.models import OllamaModel
from deepeval.test_case import LLMTestCase


def _truncate_ctx(event: dict, max_chars: int = 4000) -> list[str]:
    ctx = (event.get("retrieval_context") or {}).get("output") or ""
    ctx = str(ctx)[:max_chars]
    return [ctx] if ctx else []


def build_test_case(event: dict) -> LLMTestCase:
    return LLMTestCase(
        input=str(event["event_data"]["request"]),
        actual_output=str(event["event_data"]["response"]["output"]),
        retrieval_context=_truncate_ctx(event),
    )


def _metric_result(m) -> dict[str, Any]:
    return {
        "name": m.__class__.__name__.removesuffix("Metric"),
        "score": m.score,
        "threshold": m.threshold,
        "success": m.is_successful(),
        "reason": getattr(m, "reason", None),
        "error": getattr(m, "error", None),
    }


def run_faithfulness(test_case: LLMTestCase, judge: OllamaModel) -> dict[str, Any]:
    m = FaithfulnessMetric(threshold=0.7, model=judge, include_reason=True)
    m.measure(test_case)
    return _metric_result(m)


def run_answer_relevancy(test_case: LLMTestCase, judge: OllamaModel) -> dict[str, Any]:
    m = AnswerRelevancyMetric(threshold=0.7, model=judge, include_reason=True)
    m.measure(test_case)
    return _metric_result(m)


def run_contextual_relevancy(test_case: LLMTestCase, judge: OllamaModel) -> dict[str, Any]:
    m = ContextualRelevancyMetric(threshold=0.7, model=judge, include_reason=True)
    m.measure(test_case)
    return _metric_result(m)


def run_contextual_precision(test_case: LLMTestCase, judge: OllamaModel) -> dict[str, Any]:
    m = ContextualPrecisionMetric(threshold=0.7, model=judge, include_reason=True)
    m.measure(test_case)
    return _metric_result(m)


def run_contextual_recall(test_case: LLMTestCase, judge: OllamaModel) -> dict[str, Any]:
    m = ContextualRecallMetric(threshold=0.7, model=judge, include_reason=True)
    m.measure(test_case)
    return _metric_result(m)


def eval_function(event: dict) -> dict[str, Any]:
    test_case = build_test_case(event)

    judge = OllamaModel(
        model="qwen3:8b",
        temperature=0.0,
    )

    # sequential execution (avoid concurrency timeouts)
    metrics = [
        run_faithfulness(test_case, judge),
        run_answer_relevancy(test_case, judge),
        run_contextual_relevancy(test_case, judge),
        run_contextual_precision(test_case, judge),
        run_contextual_recall(test_case, judge),
    ]

    overall_success = all(m["success"] for m in metrics)

    return {
        "test_case": {
            "input": test_case.input,
            "actual_output": test_case.actual_output,
            "retrieval_context_len": sum(len(c) for c in (test_case.retrieval_context or [])),
        },
        "metrics": metrics,
        "success": overall_success,
    }
