"""Tests for _format_results in service.py."""
from __future__ import annotations

from deepeval_mvp.service import _format_results


def test_format_results_basic():
    results = {
        "success": True,
        "metrics": [
            {
                "name": "Faithfulness",
                "score": 0.9,
                "threshold": 0.7,
                "success": True,
                "reason": "good",
                "error": None,
            },
        ],
    }
    output = _format_results(results)
    assert "Faithfulness" in output
    assert "0.9" in output
    assert "Overall success: True" in output


def test_format_results_includes_error():
    results = {
        "success": False,
        "metrics": [
            {
                "name": "M1",
                "score": 0.3,
                "threshold": 0.7,
                "success": False,
                "reason": "bad",
                "error": "timeout",
            },
        ],
    }
    output = _format_results(results)
    assert "timeout" in output
    assert "Overall success: False" in output


def test_format_results_no_error_field_omitted():
    results = {
        "success": True,
        "metrics": [
            {
                "name": "M1",
                "score": 1.0,
                "threshold": 0.5,
                "success": True,
                "reason": "ok",
            },
        ],
    }
    output = _format_results(results)
    assert "error" not in output.lower() or "error" not in output.split("Overall")[0].lower()
