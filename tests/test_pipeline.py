from deepeval_mvp.models import AIEvent
from deepeval_mvp.pipeline import process_event


def test_process_event_skips_when_filtered(monkeypatch):
    monkeypatch.setattr(
        "deepeval_mvp.pipeline.should_evaluate",
        lambda system, event_type: False,
    )

    event = AIEvent(
        system="enterprise-rag-chatbot",
        event_type="ai-event",
        user_input="q",
        context="c",
        output="o",
        raw_meta={},
    )

    assert process_event(event) is None


def test_process_event_calls_eval_when_allowed(monkeypatch):
    monkeypatch.setattr(
        "deepeval_mvp.pipeline.should_evaluate",
        lambda system, event_type: True,
    )
    monkeypatch.setattr(
        "deepeval_mvp.pipeline.eval_function",
        lambda user_input, context, output: {"ok": True},
    )

    event = AIEvent(
        system="enterprise-rag-chatbot",
        event_type="ai-event",
        user_input="q",
        context="c",
        output="o",
        raw_meta={},
    )

    assert process_event(event) == {"ok": True}
