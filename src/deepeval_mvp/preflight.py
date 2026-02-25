from __future__ import annotations

import importlib.util
import logging
import os

from pymongo import MongoClient


def _get_env(name: str, fallback: str | None = None) -> str | None:
    val = os.getenv(name)
    if val:
        return val
    if fallback:
        return os.getenv(fallback)
    return None


def run_preflight(logger: logging.LoggerAdapter | logging.Logger) -> bool:
    """Validate the environment before starting the service.

    Checks (in order):
    1. Required env vars are present.
    2. ``ENABLE_PROMPT_ALIGNMENT=1`` implies ``PROMPT_INSTRUCTIONS`` is set.
    3. ``deepeval`` package is importable.
    4. MongoDB is reachable (single ping — MongoResultStore does NOT re-ping).

    Returns True only if *all* checks pass.
    """
    ok = True

    # ── Required env vars ─────────────────────────────────────────────────────
    mongo_uri = _get_env("MONGO_URI", "MONGODB_URI")
    mongo_db = _get_env("MONGO_DB", "MONGODB_DB")
    judge_model = os.getenv("JUDGE_MODEL")

    missing = [
        name
        for name, value in {
            "MONGO_URI": mongo_uri,
            "MONGO_DB": mongo_db,
            "JUDGE_MODEL": judge_model,
        }.items()
        if not value
    ]

    if missing:
        logger.error(
            "preflight failed: missing required env",
            extra={"stage": "preflight", "outcome": "error", "error_message": ",".join(missing)},
        )
        ok = False

    # ── PromptAlignment config coherence ──────────────────────────────────────
    # Raise early rather than letting a misconfigured metric silently poison
    # every evaluation at runtime.
    enable_pa = os.getenv("ENABLE_PROMPT_ALIGNMENT", "0").strip().lower()
    if enable_pa in {"1", "true", "yes", "y", "on"}:
        prompt_instructions = os.getenv("PROMPT_INSTRUCTIONS", "").strip()
        if not prompt_instructions:
            logger.error(
                "preflight failed: ENABLE_PROMPT_ALIGNMENT=1 but PROMPT_INSTRUCTIONS is empty",
                extra={
                    "stage": "preflight",
                    "outcome": "error",
                    "error_message": "Set PROMPT_INSTRUCTIONS or disable ENABLE_PROMPT_ALIGNMENT",
                },
            )
            ok = False

    # ── deepeval availability ─────────────────────────────────────────────────
    if importlib.util.find_spec("deepeval") is None:
        logger.error(
            "preflight failed: deepeval not installed",
            extra={
                "stage": "preflight",
                "outcome": "error",
                "error_type": "ModuleNotFoundError",
                "error_message": "deepeval",
            },
        )
        ok = False

    # ── MongoDB connectivity (authoritative ping — store skips its own ping) ──
    if mongo_uri and mongo_db:
        try:
            client = MongoClient(mongo_uri)
            client.admin.command("ping")
        except Exception as exc:  # pragma: no cover - depends on env
            logger.error(
                "preflight failed: mongo ping",
                extra={
                    "stage": "preflight",
                    "outcome": "error",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            ok = False

    if ok:
        logger.info("preflight ok", extra={"stage": "preflight", "outcome": "stored"})

    return ok
