from __future__ import annotations

import importlib.util
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from deepeval_mvp.env_utils import env_bool, env_csv, env_float, env_int


def _require_deepeval() -> None:
    if importlib.util.find_spec("deepeval") is None:
        raise ModuleNotFoundError(
            "Optional dependency 'deepeval' is not installed. "
            "Install it to run evaluation (e.g. `uv add deepeval`)."
        )


# ── _SanitizingOllamaModel ───────────────────────────────────────────────────
# Moved to module level so it can be unit-tested and subclassed independently.
# Config (model name, base_url) is passed via __init__ rather than captured
# from a closure.  The class is constructed by _build_judge() below.

class _SanitizingOllamaModel:
    """OllamaModel wrapper that:

    1. Sanitises raw LLM responses before Pydantic JSON validation
       (strips markdown code fences and U+00A0 non-breaking spaces).
    2. Optionally injects a system-level instruction into every Ollama
       request (via ``JUDGE_SYSTEM_PROMPT`` / ``JUDGE_SYSTEM_PROMPT_FILE``).
    3. Optionally streams tokens to stderr for live demo visibility
       (via ``STREAM_EVAL_OUTPUT``).

    When neither a system prompt nor streaming is configured, the call
    falls through to ``super().generate`` unchanged so there is zero
    behavioural difference from the stock OllamaModel.

    Note: the actual base class (``deepeval.models.OllamaModel``) is mixed
    in dynamically by ``_build_sanitizing_model_class()`` to avoid importing
    ``deepeval`` at module load time.
    """

    _NBSP = str.maketrans({"\xa0": " "})

    def __init__(self, *, model_name: str, base_url: str | None = None, **kwargs: Any) -> None:
        self._model_name = model_name
        self._base_url = base_url
        super().__init__(**kwargs)

    @classmethod
    def _clean(cls, text: str) -> str:
        """Normalise a raw LLM response string before JSON parsing.

        Strips markdown code fences (```json ... ```) and non-breaking
        spaces that some models emit around structured JSON outputs.
        Kept as a defensive fallback even when a system prompt discourages
        fence usage, because model compliance is not guaranteed.
        """
        cleaned = text.translate(cls._NBSP).strip()
        fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1).strip()
        return cleaned

    @staticmethod
    def _get_system_prompt() -> str | None:
        """Return the configured judge system prompt, or None if not set.

        Resolution order:
          1. ``JUDGE_SYSTEM_PROMPT_FILE`` — path to a plain-text file;
             useful for multi-line instructions.
          2. ``JUDGE_SYSTEM_PROMPT`` — inline string in .env.

        Returns None when neither is set, which preserves existing
        behaviour (no system message sent to Ollama).
        """
        file_path = os.getenv("JUDGE_SYSTEM_PROMPT_FILE", "").strip()
        if file_path:
            text = Path(file_path).read_text(encoding="utf-8").strip()
            return text or None
        inline = os.getenv("JUDGE_SYSTEM_PROMPT", "").strip()
        return inline or None

    def _call_ollama(self, prompt: Any, *, stream: bool = False) -> tuple[str, Any]:
        """Unified Ollama call that injects the system prompt and optionally
        streams tokens to stderr.

        Used by ``generate`` whenever a system prompt is configured or
        streaming is enabled.
        """
        import sys as _sys

        import ollama as _ollama  # already a project dependency

        client_kwargs: dict[str, Any] = {}
        if self._base_url:
            client_kwargs["host"] = self._base_url.rstrip("/")
        client = _ollama.Client(**client_kwargs)

        messages: list[dict[str, str]] = []
        system_prompt = self._get_system_prompt()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": str(prompt)})

        if stream:
            _sys.stderr.write("\n[judge] ")
            _sys.stderr.flush()
            chunks: list[str] = []
            for chunk in client.chat(model=self._model_name, messages=messages, stream=True):
                token: str = chunk.message.content or ""
                _sys.stderr.write(token)
                _sys.stderr.flush()
                chunks.append(token)
            _sys.stderr.write("\n")
            _sys.stderr.flush()
            return "".join(chunks), 0
        else:
            response = client.chat(model=self._model_name, messages=messages)
            return response.message.content or "", 0

    # ``schema=None`` on the super() call means we get back the raw string
    # rather than having the parent attempt (and fail) to validate it.
    # We then sanitise and validate ourselves.
    def generate(self, prompt: Any, schema: Any = None) -> Any:  # type: ignore[override]
        streaming = env_bool("STREAM_EVAL_OUTPUT", False)
        # Use _call_ollama whenever we need to inject a system prompt or
        # stream tokens.  Otherwise fall through to super() unchanged so
        # there is zero behavioural difference from the stock OllamaModel.
        if streaming or self._get_system_prompt() is not None:
            raw, cost = self._call_ollama(prompt, stream=streaming)
        else:
            raw, cost = super().generate(prompt, schema=None)  # type: ignore[misc]
        if schema is not None and isinstance(raw, str):
            return schema.model_validate_json(self._clean(raw)), cost
        return raw, cost

    async def a_generate(self, prompt: Any, schema: Any = None) -> Any:  # type: ignore[override]
        # NOTE: async path does NOT support system-prompt injection or streaming
        # yet. If a system prompt is configured, warn loudly rather than
        # silently dropping it.
        if self._get_system_prompt() is not None:
            import warnings
            warnings.warn(
                "JUDGE_SYSTEM_PROMPT is configured but a_generate() does not "
                "support system-prompt injection.  The system prompt will be "
                "ignored for async metrics.  Use METRIC_ASYNC_MODE=false or "
                "implement async _call_ollama.",
                UserWarning,
                stacklevel=2,
            )
        raw, cost = await super().a_generate(prompt, schema=None)  # type: ignore[misc]
        if schema is not None and isinstance(raw, str):
            return schema.model_validate_json(self._clean(raw)), cost
        return raw, cost


class _OpenRouterModel:
    """DeepEvalBaseLLM wrapper that calls OpenRouter's OpenAI-compatible API.

    Reuses ``_SanitizingOllamaModel._clean`` for response sanitisation and
    ``_SanitizingOllamaModel._get_system_prompt`` for optional system-prompt
    injection so that both backends behave consistently.

    The actual base class (``deepeval.models.DeepEvalBaseLLM``) is mixed in
    dynamically by ``_build_openrouter_model_class()`` to avoid importing
    ``deepeval`` at module load time.
    """

    def __init__(self, *, model_name: str, api_key: str, temperature: float = 0.0) -> None:
        self._model_name = model_name
        self._api_key = api_key
        self._temperature = temperature

    def load_model(self) -> Any:
        return self._model_name

    def get_model_name(self) -> str:
        return self._model_name

    def _build_client(self) -> Any:
        from openai import OpenAI  # pylint: disable=import-outside-toplevel

        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self._api_key,
            max_retries=env_int("OPENROUTER_MAX_RETRIES", 6),
        )

    def generate(self, prompt: Any, schema: Any = None) -> Any:
        import sys as _sys

        client = self._build_client()
        messages: list[dict[str, str]] = []
        system_prompt = _SanitizingOllamaModel._get_system_prompt()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": str(prompt)})

        streaming = env_bool("STREAM_EVAL_OUTPUT", False)

        if streaming:
            _sys.stderr.write("\n[judge] ")
            _sys.stderr.flush()
            chunks: list[str] = []
            response = client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                temperature=self._temperature,
                stream=True,
            )
            for chunk in response:
                token = chunk.choices[0].delta.content or ""
                _sys.stderr.write(token)
                _sys.stderr.flush()
                chunks.append(token)
            _sys.stderr.write("\n")
            _sys.stderr.flush()
            raw = "".join(chunks)
        else:
            response = client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                temperature=self._temperature,
            )
            raw = response.choices[0].message.content or ""

        if schema is not None and isinstance(raw, str):
            return schema.model_validate_json(_SanitizingOllamaModel._clean(raw))
        return raw

    async def a_generate(self, prompt: Any, schema: Any = None) -> Any:
        from openai import AsyncOpenAI  # pylint: disable=import-outside-toplevel

        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self._api_key,
            max_retries=env_int("OPENROUTER_MAX_RETRIES", 6),
        )

        messages: list[dict[str, str]] = []
        system_prompt = _SanitizingOllamaModel._get_system_prompt()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": str(prompt)})

        response = await client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            temperature=self._temperature,
        )
        raw = response.choices[0].message.content or ""

        if schema is not None and isinstance(raw, str):
            return schema.model_validate_json(_SanitizingOllamaModel._clean(raw))
        return raw


def _build_sanitizing_model_class() -> type:
    """Dynamically build the concrete class with OllamaModel as a base.

    This avoids importing ``deepeval`` at module load time (which would break
    environments where ``deepeval`` is not installed, e.g. lightweight CI).
    """
    _require_deepeval()
    from deepeval.models import OllamaModel  # pylint: disable=import-outside-toplevel

    # Create a new class that inherits from both _SanitizingOllamaModel (for
    # our custom logic) and OllamaModel (for the deepeval interface).
    # MRO: SanitizingJudge -> _SanitizingOllamaModel -> OllamaModel -> ...
    cls = type(
        "SanitizingJudge",
        (_SanitizingOllamaModel, OllamaModel),  # type: ignore[misc]
        {},
    )
    return cls


def _build_openrouter_model_class() -> type:
    """Dynamically build the OpenRouter model class with DeepEvalBaseLLM as a base."""
    _require_deepeval()
    from deepeval.models import DeepEvalBaseLLM  # pylint: disable=import-outside-toplevel

    cls = type(
        "OpenRouterJudge",
        (_OpenRouterModel, DeepEvalBaseLLM),  # type: ignore[misc]
        {},
    )
    return cls


def _build_judge() -> Any:
    model = os.getenv("JUDGE_MODEL")
    if not model:
        raise RuntimeError("JUDGE_MODEL is not set in environment (.env).")

    backend = os.getenv("JUDGE_BACKEND", "ollama").strip().lower()

    if backend == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "JUDGE_BACKEND=openrouter but OPENROUTER_API_KEY is not set."
            )
        cls = _build_openrouter_model_class()
        return cls(
            model_name=model,
            api_key=api_key,
            temperature=env_float("JUDGE_TEMPERATURE", 0.0),
        )

    if backend != "ollama":
        raise RuntimeError(
            f"Unknown JUDGE_BACKEND={backend!r}. Supported: 'ollama', 'openrouter'."
        )

    kwargs: dict[str, Any] = {
        "model": model,
        "model_name": model,
        "temperature": env_float("JUDGE_TEMPERATURE", 0.0),
    }

    base_url = os.getenv("LOCAL_MODEL_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url

    cls = _build_sanitizing_model_class()
    return cls(**kwargs)


@lru_cache(maxsize=1)
def _get_judge() -> Any:
    """Return the cached judge instance, building it on first call.

    The judge (OllamaModel) is stateless after construction — it holds no
    per-measurement state — so it is safe to reuse across events.  The cache
    is process-scoped; call ``_get_judge.cache_clear()`` in tests that need a
    fresh instance.
    """
    return _build_judge()


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


def _non_negative_env_int(name: str, default: int) -> int:
    """Return a non-negative integer from env, clamping invalid negatives."""
    return max(0, env_int(name, default))


def _run_metric(m: Any, test_case: Any, name_override: str | None = None) -> dict[str, Any]:
    """Run a single metric with optional retry on exception.

    ``EVAL_RETRIES`` (default 0) controls how many times to retry on failure.
    ``EVAL_RETRY_BACKOFF_MS`` (default 200) is the initial back-off in ms;
    each subsequent attempt doubles the delay (exponential back-off).
    """
    max_retries = _non_negative_env_int("EVAL_RETRIES", 0)
    backoff_ms = _non_negative_env_int("EVAL_RETRY_BACKOFF_MS", 200)

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            m.measure(test_case)
            return _metric_result(m, name_override=name_override)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep((backoff_ms * (2 ** attempt)) / 1000)

    if last_exc is not None:
        raise last_exc

    # Defensive fallback: should be unreachable because at least one attempt runs.
    raise RuntimeError("Metric execution failed without raising an exception.")


def _build_metrics(judge: Any) -> list[Any]:
    """Build fresh metric instances for a single evaluation run.

    Metrics are intentionally NOT cached — each ``measure()`` call mutates
    instance state (score, reason, is_successful).  Reusing instances across
    events would mix up results from different events.
    """
    _require_deepeval()
    from deepeval.metrics import (  # pylint: disable=import-outside-toplevel
        AnswerRelevancyMetric,
        ContextualRelevancyMetric,
        FaithfulnessMetric,
        GEval,
        PromptAlignmentMetric,
    )
    from deepeval.test_case import LLMTestCaseParams  # pylint: disable=import-outside-toplevel

    enabled = set(
        env_csv(
            "ENABLED_METRICS",
            "faithfulness,answer_relevancy,contextual_relevancy,completeness,informativeness",
        )
    )

    metrics: list[Any] = []

    if "faithfulness" in enabled:
        metrics.append(
            FaithfulnessMetric(
                threshold=env_float("THRESHOLD_FAITHFULNESS", 0.7),
                model=judge,
                include_reason=env_bool("INCLUDE_REASON_FAITHFULNESS", True),
                async_mode=env_bool("METRIC_ASYNC_MODE", False),
            )
        )

    if "answer_relevancy" in enabled:
        metrics.append(
            AnswerRelevancyMetric(
                threshold=env_float("THRESHOLD_ANSWER_RELEVANCY", 0.7),
                model=judge,
                include_reason=env_bool("INCLUDE_REASON_ANSWER_RELEVANCY", True),
                async_mode=env_bool("METRIC_ASYNC_MODE", False),
            )
        )

    if "contextual_relevancy" in enabled:
        metrics.append(
            ContextualRelevancyMetric(
                threshold=env_float("THRESHOLD_CONTEXTUAL_RELEVANCY", 0.7),
                model=judge,
                include_reason=env_bool("INCLUDE_REASON_CONTEXTUAL_RELEVANCY", True),
                async_mode=env_bool("METRIC_ASYNC_MODE", False),
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
                threshold=env_float("THRESHOLD_COMPLETENESS", 0.7),
                model=judge,
                evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                async_mode=env_bool("METRIC_ASYNC_MODE", False),
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
                threshold=env_float("THRESHOLD_INFORMATIVENESS", 0.7),
                model=judge,
                evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                async_mode=env_bool("METRIC_ASYNC_MODE", False),
            )
        )

    if env_bool("ENABLE_PROMPT_ALIGNMENT", False):
        instructions = env_csv("PROMPT_INSTRUCTIONS", "")
        if not instructions:
            # Fail loudly rather than silently poisoning every evaluation with a
            # fixed-fail metric.  Preflight also catches this before the service starts.
            raise RuntimeError(
                "ENABLE_PROMPT_ALIGNMENT=1 but PROMPT_INSTRUCTIONS is empty. "
                "Set PROMPT_INSTRUCTIONS to a comma-separated list of instruction strings, "
                "or set ENABLE_PROMPT_ALIGNMENT=0."
            )
        metrics.append(
            PromptAlignmentMetric(
                prompt_instructions=instructions,
                threshold=env_float("PROMPT_ALIGNMENT_THRESHOLD", 0.7),
                model=judge,
                include_reason=env_bool("PROMPT_ALIGNMENT_INCLUDE_REASON", True),
                strict_mode=env_bool("PROMPT_ALIGNMENT_STRICT_MODE", False),
                async_mode=env_bool("PROMPT_ALIGNMENT_ASYNC_MODE", False),
                verbose_mode=env_bool("PROMPT_ALIGNMENT_VERBOSE_MODE", False),
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

    judge = _get_judge()
    metric_objs = _build_metrics(judge)

    results: list[dict[str, Any]] = []
    for m in metric_objs:
        name_override = getattr(m, "name", None)
        results.append(_run_metric(m, test_case, name_override=name_override))

    metric_outcomes = [bool(r.get("success")) for r in results if r.get("success") is not None]
    overall_success = bool(metric_outcomes) and all(metric_outcomes)

    return {
        "eval_version": os.getenv("EVAL_VERSION", "unknown"),
        "test_case": {
            "input": user_input,
            "actual_output": output,
            "retrieval_context_len": len(context),
        },
        "metrics": results,
        "success": overall_success,
    }
