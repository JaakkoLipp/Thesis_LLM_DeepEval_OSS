from deepeval_mvp.filtering import should_evaluate


def test_should_evaluate_true_for_allowed(monkeypatch):
    monkeypatch.setattr(
        "deepeval_mvp.filtering.ALLOWED_SYSTEMS", {"enterprise-rag-chatbot"}, raising=False
    )
    monkeypatch.setattr(
        "deepeval_mvp.filtering.ALLOWED_EVENT_TYPES", {"ai-event"}, raising=False
    )

    assert should_evaluate("enterprise-rag-chatbot", "ai-event") is True


def test_should_evaluate_false_for_wrong_system(monkeypatch):
    monkeypatch.setattr(
        "deepeval_mvp.filtering.ALLOWED_SYSTEMS", {"enterprise-rag-chatbot"}, raising=False
    )
    monkeypatch.setattr(
        "deepeval_mvp.filtering.ALLOWED_EVENT_TYPES", {"ai-event"}, raising=False
    )

    assert should_evaluate("wrong-system", "ai-event") is False


def test_should_evaluate_false_for_wrong_event_type(monkeypatch):
    monkeypatch.setattr(
        "deepeval_mvp.filtering.ALLOWED_SYSTEMS", {"enterprise-rag-chatbot"}, raising=False
    )
    monkeypatch.setattr(
        "deepeval_mvp.filtering.ALLOWED_EVENT_TYPES", {"ai-event"}, raising=False
    )

    assert should_evaluate("enterprise-rag-chatbot", "not-ai-event") is False
