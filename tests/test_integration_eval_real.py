import os
from pathlib import Path

import pytest

from deepeval_mvp.get_message import get_event
from deepeval_mvp.pipeline import process_event

pytestmark = pytest.mark.system


@pytest.mark.skipif(os.getenv("RUN_SYSTEM") != "1", reason="RUN_SYSTEM!=1")
@pytest.mark.skipif(not os.getenv("JUDGE_MODEL"), reason="JUDGE_MODEL not set")
def test_eval_function_real_stack():
    fixture = Path(__file__).parent / "fixtures" / "valid_sample.txt"
    event = get_event(str(fixture))

    res = process_event(event)
    assert res is not None  # fixture should be allowed by filtering rules

    # Assert schema, not exact scores (scores are model-dependent)
    assert isinstance(res, dict)
    assert "metrics" in res and isinstance(res["metrics"], list)
    assert "success" in res and isinstance(res["success"], bool)

    for m in res["metrics"]:
        assert "name" in m
        assert "score" in m
        assert "threshold" in m
        assert "success" in m
