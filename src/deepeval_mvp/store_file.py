"""FileResultStore — writes evaluation results to individual files.

Activated by setting the environment variable ``OUTPUT_TO_FILE=1``.
The output directory defaults to ``output/`` at the repository root but can
be overridden with ``OUTPUT_DIR``.

Output format is selected by ``OUTPUT_FILE_FORMAT``:

- ``text`` (default): human-readable ``.txt`` files
- ``json``: structured ``.json`` files

Implements the same :class:`ResultStore` protocol as :class:`MongoResultStore`,
so it is a drop-in replacement everywhere the protocol is expected.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from deepeval_mvp.models import AIEvent
from deepeval_mvp.store_mongo import _event_id_from_payload, _kafka_id, _kafka_id_is_usable


def _sanitize_filename(event_id: str) -> str:
    """Turn an event_id into a safe, unique filename (without extension)."""
    # Replace characters that are problematic on most file systems.
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", event_id)
    # Truncate to a reasonable length; append a short hash to avoid collisions.
    if len(safe) > 120:
        short_hash = hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:12]
        safe = safe[:120] + "_" + short_hash
    return safe


def _default_output_dir() -> Path:
    """Resolve the output directory from env or fall back to ``<repo>/output``."""
    explicit = os.getenv("OUTPUT_DIR")
    if explicit:
        return Path(explicit).resolve()
    # Walk upwards from this file to reach the repo root (two levels above src/).
    return Path(__file__).resolve().parents[2] / "output"


def _output_file_format() -> Literal["text", "json"]:
    """Resolve the file output format from ``OUTPUT_FILE_FORMAT``."""
    raw = (os.getenv("OUTPUT_FILE_FORMAT") or "text").strip().lower()
    if raw == "json":
        return "json"
    return "text"


class FileResultStore:
    """Persist evaluation results as text or JSON files.

    Each event produces one file named after its event ID inside the configured
    output directory. Duplicate detection is based on whether the file already
    exists on disk.
    """

    def __init__(self, output_dir: Path | str | None = None) -> None:
        self._dir = Path(output_dir) if output_dir else _default_output_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._format: Literal["text", "json"] = _output_file_format()
        self._suffix = ".json" if self._format == "json" else ".txt"

    # ── helpers shared with MongoResultStore ──────────────────────────────

    def compute_event_id(self, event: AIEvent) -> str:
        kid = _kafka_id(event.raw_meta)
        if kid and _kafka_id_is_usable(kid):
            return kid
        return _event_id_from_payload(event.raw_meta, event.user_input, event.output)

    def _path_for(self, event_id: str) -> Path:
        return self._dir / f"{_sanitize_filename(event_id)}{self._suffix}"

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ── ResultStore protocol ─────────────────────────────────────────────

    def claim_event(self, event: AIEvent, owner_id: str) -> tuple[str, bool]:
        event_id = self.compute_event_id(event)
        path = self._path_for(event_id)
        if path.exists():
            return event_id, False  # already processed
        # "Claim" by writing a placeholder to prevent races in the
        # (unlikely) multi-process scenario.
        if self._format == "json":
            self._write_json(
                path,
                {
                    "event_id": event_id,
                    "status": "processing",
                    "owner_id": owner_id,
                    "claimed_at": datetime.now(UTC).isoformat(),
                },
            )
        else:
            path.write_text(f"# claimed by {owner_id}\n", encoding="utf-8")
        return event_id, True

    def release_claim(self, event_id: str) -> None:
        path = self._path_for(event_id)
        if path.exists():
            path.unlink()

    def mark_done(self, event_id: str, event: AIEvent, evaluation: dict[str, Any]) -> None:
        now = datetime.now(UTC).isoformat()
        eval_version = os.getenv("EVAL_VERSION", "unknown")
        if self._format == "json":
            self._write_json(
                self._path_for(event_id),
                {
                    "event_id": event_id,
                    "status": "done",
                    "eval_version": eval_version,
                    "stored_at": now,
                    "meta": {
                        "system": event.system,
                        "event_type": event.event_type,
                        "session_id": event.raw_meta.get("session_id", ""),
                        "time_stamp": event.raw_meta.get("time_stamp", ""),
                    },
                    "payload": {
                        "user_input": event.user_input,
                        "output": event.output,
                        "context": event.context,
                    },
                    "evaluation": evaluation,
                },
            )
            return

        lines: list[str] = [
            f"event_id     : {event_id}",
            "status       : done",
            f"eval_version : {eval_version}",
            f"stored_at    : {now}",
            "",
            "── Meta ────────────────────────────────────────",
            f"system       : {event.system}",
            f"event_type   : {event.event_type}",
            f"session_id   : {event.raw_meta.get('session_id', '')}",
            f"time_stamp   : {event.raw_meta.get('time_stamp', '')}",
            "",
            "── Payload ─────────────────────────────────────",
            f"user_input   : {event.user_input}",
            f"output       : {event.output}",
            f"context      : {event.context}",
            "",
            "── Evaluation ──────────────────────────────────",
        ]

        for metric in evaluation.get("metrics", []):
            lines.append(f"  [{metric.get('name', '?')}]")
            lines.append(f"    score     : {metric.get('score')}")
            lines.append(f"    threshold : {metric.get('threshold')}")
            lines.append(f"    success   : {metric.get('success')}")
            lines.append(f"    reason    : {metric.get('reason', '')}")
            if metric.get("error"):
                lines.append(f"    error     : {metric['error']}")

        lines.append("")
        lines.append(f"overall_success : {evaluation.get('success')}")
        lines.append("")

        self._path_for(event_id).write_text("\n".join(lines), encoding="utf-8")

    def mark_error(
        self,
        event_id: str,
        error_type: str,
        error_message: str,
        *,
        event: AIEvent | None = None,
        traceback_text: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        max_chars = int(os.getenv("ERROR_TRACEBACK_MAX_CHARS", "2000"))
        tb = (traceback_text or "")[:max_chars]

        if self._format == "json":
            payload: dict[str, Any] = {
                "event_id": event_id,
                "status": "error",
                "stored_at": now,
                "error": {
                    "type": error_type,
                    "message": error_message,
                },
            }

            if event is not None:
                payload["meta"] = {
                    "system": event.system,
                    "event_type": event.event_type,
                    "session_id": event.raw_meta.get("session_id", ""),
                    "time_stamp": event.raw_meta.get("time_stamp", ""),
                }
                payload["payload"] = {
                    "user_input": event.user_input,
                    "output": event.output,
                    "context": event.context,
                }

            if tb:
                payload["traceback"] = tb

            self._write_json(self._path_for(event_id), payload)
            return

        lines: list[str] = [
            f"event_id      : {event_id}",
            "status        : error",
            f"stored_at     : {now}",
            "",
            f"error_type    : {error_type}",
            f"error_message : {error_message}",
        ]

        if event is not None:
            lines += [
                "",
                "── Meta ────────────────────────────────────────",
                f"system        : {event.system}",
                f"event_type    : {event.event_type}",
                f"session_id    : {event.raw_meta.get('session_id', '')}",
                f"time_stamp    : {event.raw_meta.get('time_stamp', '')}",
                "",
                "── Payload ─────────────────────────────────────",
                f"user_input    : {event.user_input}",
                f"output        : {event.output}",
                f"context       : {event.context}",
            ]

        if tb:
            lines += [
                "",
                "── Traceback ───────────────────────────────────",
                tb,
            ]

        lines.append("")
        self._path_for(event_id).write_text("\n".join(lines), encoding="utf-8")
