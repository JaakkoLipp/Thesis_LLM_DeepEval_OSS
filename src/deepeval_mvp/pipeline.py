from __future__ import annotations

from typing import Literal
from typing import Any
from typing import TypedDict

from deepeval_mvp.eval import eval_function
from deepeval_mvp.filtering import should_evaluate
from deepeval_mvp.models import AIEvent


class PipelineOutcome(TypedDict):
    action: Literal["evaluated", "skipped"]
    evaluation: dict[str, Any] | None


def run_pipeline(event: AIEvent) -> PipelineOutcome:
    if not should_evaluate(event.system, event.event_type):
        return {"action": "skipped", "evaluation": None}

    evaluation = eval_function(event.user_input, event.context, event.output)
    return {"action": "evaluated", "evaluation": evaluation}


def process_event(event: AIEvent) -> dict[str, Any] | None:
    outcome = run_pipeline(event)
    return outcome["evaluation"]
