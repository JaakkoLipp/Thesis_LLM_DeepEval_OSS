from __future__ import annotations

from typing import Any

from deepeval_mvp.eval import eval_function
from deepeval_mvp.models import AIEvent


def process_event(event: AIEvent) -> dict[str, Any]:
    """
    Evaluate a single AIEvent and return the evaluation result dict.

    Filtering must already have been applied by the caller (service layer).
    This function is a pure evaluator — it never returns None.
    """
    return eval_function(event.user_input, event.context, event.output)
