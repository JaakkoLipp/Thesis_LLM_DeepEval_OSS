from pathlib import Path

import pytest

from deepeval_mvp.get_message import get_event, get_message
from deepeval_mvp.models import AIEvent


def test_get_message_parses_valid_fixture():
    fixture = Path(__file__).parent / "fixtures" / "valid_sample.txt"
    meta, (user_input, context, output) = get_message(str(fixture))

    assert meta["system"] == "enterprise-rag-chatbot"
    assert meta["event_type"] == "ai-event"
    assert isinstance(user_input, str) and user_input
    assert isinstance(context, str)
    assert isinstance(output, str) and output


def test_get_event_returns_aievent():
    fixture = Path(__file__).parent / "fixtures" / "valid_sample.txt"
    event = get_event(str(fixture))

    assert isinstance(event, AIEvent)
    assert event.system == "enterprise-rag-chatbot"
    assert event.event_type == "ai-event"
    assert isinstance(event.user_input, str) and event.user_input
    assert isinstance(event.context, str)
    assert isinstance(event.output, str) and event.output
    assert isinstance(event.raw_meta, dict)


def test_get_message_raises_when_pattern_missing(tmp_path):
    p = tmp_path / "bad.txt"
    p.write_text("no value=b'''...''' here")

    with pytest.raises(ValueError):
        get_message(str(p))
