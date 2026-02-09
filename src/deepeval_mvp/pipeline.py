from __future__ import annotations

from typing import Any

from deepeval_mvp.eval import eval_function
from deepeval_mvp.filtering import should_evaluate
from deepeval_mvp.models import AIEvent


def process_event(event: AIEvent) -> dict[str, Any] | None:
    """
    Process a single AIEvent.
    Returns:
      - dict with evaluation results if evaluated
      - None if skipped by filtering rules
    """
    if not should_evaluate(event.system, event.event_type):
        return None

    return eval_function(event.user_input, event.context, event.output)
