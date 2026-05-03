from __future__ import annotations

import json

from deepeval_mvp.store_file import FileResultStore


def _sample_evaluation(success: bool) -> dict[str, object]:
    return {
        "success": success,
        "metrics": [
            {
                "name": "faithfulness",
                "score": 0.9,
                "threshold": 0.7,
                "success": success,
                "reason": "ok",
                "error": None,
            }
        ],
    }


def test_file_result_store_default_text_output(tmp_path, sample_aievent):
    store = FileResultStore(output_dir=tmp_path)

    event_id, claimed = store.claim_event(sample_aievent, owner_id="worker-1")
    assert claimed is True

    store.mark_done(event_id, sample_aievent, _sample_evaluation(success=True))

    out_files = list(tmp_path.glob("*.txt"))
    assert len(out_files) == 1

    body = out_files[0].read_text(encoding="utf-8")
    assert "status       : done" in body
    assert "overall_success : True" in body


def test_file_result_store_json_output_for_done(tmp_path, sample_aievent, monkeypatch):
    monkeypatch.setenv("OUTPUT_FILE_FORMAT", "json")
    store = FileResultStore(output_dir=tmp_path)

    event_id, claimed = store.claim_event(sample_aievent, owner_id="worker-1")
    assert claimed is True

    duplicate_id, duplicate_claimed = store.claim_event(sample_aievent, owner_id="worker-2")
    assert duplicate_id == event_id
    assert duplicate_claimed is False

    store.mark_done(event_id, sample_aievent, _sample_evaluation(success=True))

    out_files = list(tmp_path.glob("*.json"))
    assert len(out_files) == 1

    payload = json.loads(out_files[0].read_text(encoding="utf-8"))
    assert payload["event_id"] == event_id
    assert payload["status"] == "done"
    assert payload["payload"]["output"] == sample_aievent.output
    assert payload["evaluation"]["success"] is True


def test_file_result_store_json_output_for_error(tmp_path, sample_aievent, monkeypatch):
    monkeypatch.setenv("OUTPUT_FILE_FORMAT", "json")
    monkeypatch.setenv("ERROR_TRACEBACK_MAX_CHARS", "8")

    store = FileResultStore(output_dir=tmp_path)

    event_id, claimed = store.claim_event(sample_aievent, owner_id="worker-1")
    assert claimed is True

    store.mark_error(
        event_id,
        "ValueError",
        "broken evaluation",
        event=sample_aievent,
        traceback_text="0123456789",
    )

    out_files = list(tmp_path.glob("*.json"))
    assert len(out_files) == 1

    payload = json.loads(out_files[0].read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["error"]["type"] == "ValueError"
    assert payload["error"]["message"] == "broken evaluation"
    assert payload["traceback"] == "01234567"
    assert payload["meta"]["system"] == sample_aievent.system
