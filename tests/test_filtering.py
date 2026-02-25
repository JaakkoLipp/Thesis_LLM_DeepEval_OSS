from deepeval_mvp.filtering import should_evaluate


def test_should_evaluate_true_for_allowed(monkeypatch):
    monkeypatch.setenv("ALLOWED_SYSTEMS", "enterprise-rag-chatbot")
    monkeypatch.setenv("ALLOWED_EVENT_TYPES", "ai-event")

    assert should_evaluate("enterprise-rag-chatbot", "ai-event") is True


def test_should_evaluate_false_for_wrong_system(monkeypatch):
    monkeypatch.setenv("ALLOWED_SYSTEMS", "enterprise-rag-chatbot")
    monkeypatch.setenv("ALLOWED_EVENT_TYPES", "ai-event")

    assert should_evaluate("wrong-system", "ai-event") is False


def test_should_evaluate_false_for_wrong_event_type(monkeypatch):
    monkeypatch.setenv("ALLOWED_SYSTEMS", "enterprise-rag-chatbot")
    monkeypatch.setenv("ALLOWED_EVENT_TYPES", "ai-event")

    assert should_evaluate("enterprise-rag-chatbot", "not-ai-event") is False


def test_should_evaluate_supports_multiple_allowed_values(monkeypatch):
    monkeypatch.setenv("ALLOWED_SYSTEMS", "enterprise-rag-chatbot,test-system,analytics-bot")
    monkeypatch.setenv("ALLOWED_EVENT_TYPES", "ai-event,query-event")

    assert should_evaluate("test-system", "query-event") is True
    assert should_evaluate("analytics-bot", "ai-event") is True
    assert should_evaluate("unknown-system", "ai-event") is False
