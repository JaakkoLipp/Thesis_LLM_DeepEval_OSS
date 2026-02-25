from deepeval_mvp.models import AIEvent
from deepeval_mvp.pipeline import process_event


def _make_event() -> AIEvent:
    return AIEvent(
        system="enterprise-rag-chatbot",
        event_type="ai-event",
        user_input="q",
        context="c",
        output="o",
        raw_meta={},
    )


def test_process_event_calls_eval_function(monkeypatch):
    """process_event is a pure evaluator — it must call eval_function and return its result."""
    monkeypatch.setattr(
        "deepeval_mvp.pipeline.eval_function",
        lambda user_input, context, output: {"ok": True},
    )

    result = process_event(_make_event())

    assert result == {"ok": True}


def test_process_event_forwards_event_fields_to_eval(monkeypatch):
    """Verify that the correct fields from AIEvent are forwarded to eval_function."""
    captured: dict = {}

    def _fake_eval(user_input: str, context: str, output: str):
        captured["user_input"] = user_input
        captured["context"] = context
        captured["output"] = output
        return {"captured": True}

    monkeypatch.setattr("deepeval_mvp.pipeline.eval_function", _fake_eval)

    event = AIEvent(
        system="enterprise-rag-chatbot",
        event_type="ai-event",
        user_input="what is X?",
        context="some context",
        output="the answer",
        raw_meta={},
    )
    process_event(event)

    assert captured["user_input"] == "what is X?"
    assert captured["context"] == "some context"
    assert captured["output"] == "the answer"
