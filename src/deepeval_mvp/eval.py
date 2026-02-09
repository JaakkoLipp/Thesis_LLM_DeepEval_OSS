from __future__ import annotations

import os
import importlib.util
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    # Only for type checking; these imports do not run at runtime.
    from deepeval.models import OllamaModel
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams


def _require_deepeval() -> None:
    if importlib.util.find_spec("deepeval") is None:
        raise ModuleNotFoundError(
            "Optional dependency 'deepeval' is not installed. "
            "Install it to run evaluation (e.g. `uv add deepeval`)."
        )


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    return float(v)


def _parse_csv_env(name: str, default_csv: str = "") -> list[str]:
    raw = os.getenv(name, default_csv) or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


def _build_judge() -> Any:
    _require_deepeval()
    from deepeval.models import OllamaModel  # pylint: disable=import-outside-toplevel

    model = os.getenv("JUDGE_MODEL")
    if not model:
        raise RuntimeError("JUDGE_MODEL is not set in environment (.env).")

    return OllamaModel(model=model, temperature=_env_float("JUDGE_TEMPERATURE", 0.0))


def _metric_result(m: Any, name_override: str | None = None) -> dict[str, Any]:
    name = name_override or m.__class__.__name__.removesuffix("Metric")
    return {
        "name": name,
        "score": getattr(m, "score", None),
        "threshold": getattr(m, "threshold", None),
        "success": m.is_successful() if hasattr(m, "is_successful") else None,
        "reason": getattr(m, "reason", None),
        "error": getattr(m, "error", None),
    }


def _run_metric(m: Any, test_case: Any, name_override: str | None = None) -> dict[str, Any]:
    m.measure(test_case)
    return _metric_result(m, name_override=name_override)


def _build_metrics(judge: Any) -> list[Any]:
    _require_deepeval()
    from deepeval.metrics import (  # pylint: disable=import-outside-toplevel
        AnswerRelevancyMetric,
        ContextualRelevancyMetric,
        FaithfulnessMetric,
        GEval,
        PromptAlignmentMetric,
    )
    from deepeval.test_case import LLMTestCaseParams # pylint: disable=import-outside-toplevel

    enabled = set(
        _parse_csv_env(
            "ENABLED_METRICS",
            "faithfulness,answer_relevancy,contextual_relevancy,completeness,informativeness",
        )
    )

    metrics: list[Any] = []

    if "faithfulness" in enabled:
        metrics.append(
            FaithfulnessMetric(
                threshold=_env_float("THRESHOLD_FAITHFULNESS", 0.7),
                model=judge,
                include_reason=_env_bool("INCLUDE_REASON_FAITHFULNESS", True),
            )
        )

    if "answer_relevancy" in enabled:
        metrics.append(
            AnswerRelevancyMetric(
                threshold=_env_float("THRESHOLD_ANSWER_RELEVANCY", 0.7),
                model=judge,
                include_reason=_env_bool("INCLUDE_REASON_ANSWER_RELEVANCY", True),
            )
        )

    if "contextual_relevancy" in enabled:
        metrics.append(
            ContextualRelevancyMetric(
                threshold=_env_float("THRESHOLD_CONTEXTUAL_RELEVANCY", 0.7),
                model=judge,
                include_reason=_env_bool("INCLUDE_REASON_CONTEXTUAL_RELEVANCY", True),
            )
        )

    if "completeness" in enabled:
        metrics.append(
            GEval(
                name="Completeness",
                evaluation_steps=[
                    "Extract the explicit requirements from the user input.",
                    "Check whether the actual output addresses each requirement.",
                    "Penalize missing required parts; ignore style.",
                    "Return a score between 0 and 10 where 10 means all requirements are fully met and 0 means none are met.",
                    "Output format exactly: SCORE: <float> REASON: <text>",
                ],
                threshold=_env_float("THRESHOLD_COMPLETENESS", 0.7),
                model=judge,
                evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            )
        )

    if "informativeness" in enabled:
        metrics.append(
            GEval(
                name="Informativeness",
                evaluation_steps=[
                    "Determine whether the actual output provides specific, useful information to answer the input.",
                    "Penalize vague filler or non-answers; reward concrete relevant details.",
                    "Return a score between 0 and 10 where 10 is highly specific and informative and 0 is not informative.",
                    "Output format exactly: SCORE: <float> REASON: <text>",
                ],
                threshold=_env_float("THRESHOLD_INFORMATIVENESS", 0.7),
                model=judge,
                evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            )
        )

    if _env_bool("ENABLE_PROMPT_ALIGNMENT", False):
        instructions = _parse_csv_env("PROMPT_INSTRUCTIONS", "")
        if not instructions:
            metrics.append(
                GEval(
                    name="PromptAlignmentConfigError",
                    evaluation_steps=[
                        "Return score 0 as PROMPT_INSTRUCTIONS is empty and a short error message",
                    ],
                    threshold=1.0,
                    model=judge,
                    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                )
            )
        else:
            metrics.append(
                PromptAlignmentMetric(
                    prompt_instructions=instructions,
                    threshold=_env_float("PROMPT_ALIGNMENT_THRESHOLD", 0.7),
                    model=judge,
                    include_reason=_env_bool("PROMPT_ALIGNMENT_INCLUDE_REASON", True),
                    strict_mode=_env_bool("PROMPT_ALIGNMENT_STRICT_MODE", False),
                    async_mode=_env_bool("PROMPT_ALIGNMENT_ASYNC_MODE", False),
                    verbose_mode=_env_bool("PROMPT_ALIGNMENT_VERBOSE_MODE", False),
                )
            )

    return metrics


def eval_function(user_input: str, context: str, output: str) -> dict[str, Any]:
    _require_deepeval()
    from deepeval.test_case import LLMTestCase  # pylint: disable=import-outside-toplevel

    max_ctx_chars = int(os.getenv("MAX_CONTEXT_CHARS", "4000"))

    test_case = LLMTestCase(
        input=user_input,
        actual_output=output,
        retrieval_context=[context[:max_ctx_chars]] if context else [],
    )

    judge = _build_judge()
    metric_objs = _build_metrics(judge)

    results: list[dict[str, Any]] = []
    for m in metric_objs:
        name_override = getattr(m, "name", None)
        results.append(_run_metric(m, test_case, name_override=name_override))

    overall_success = all(
        bool(r.get("success")) for r in results if r.get("success") is not None
    )

    return {
        "test_case": {
            "input": user_input,
            "actual_output": output,
            "retrieval_context_len": len(context),
        },
        "metrics": results,
        "success": overall_success,
    }
