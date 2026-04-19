from __future__ import annotations

import importlib.util
import logging
import os
from collections.abc import Callable

from deepeval_mvp.env_utils import env_bool


def _get_env(name: str, fallback: str | None = None) -> str | None:
    val = os.getenv(name)
    if val:
        return val
    if fallback:
        return os.getenv(fallback)
    return None


def _default_db_ping(uri: str) -> None:
    """Default database connectivity check using pymongo.

    The production fork should supply its own callable (e.g. CosmosDB health
    check) via ``run_preflight(db_ping=...)`` instead.
    """
    from pymongo import MongoClient
    client = MongoClient(uri)
    client.admin.command("ping")


def run_preflight(
    logger: logging.LoggerAdapter | logging.Logger,
    *,
    db_ping: Callable[[str], None] | None = None,
) -> bool:
    """Validate the environment before starting the service.

    Checks (in order):
    1. Required env vars are present.
    2. ``ENABLE_PROMPT_ALIGNMENT=1`` implies ``PROMPT_INSTRUCTIONS`` is set.
    3. ``deepeval`` package is importable.
    4. Database is reachable via *db_ping* (defaults to MongoDB ping).

    The *db_ping* callable receives the connection URI and should raise on
    failure.  Pass a custom function for CosmosDB or any other backend.

    Returns True only if *all* checks pass.
    """
    if db_ping is None:
        db_ping = _default_db_ping

    ok = True

    # ── Required env vars ─────────────────────────────────────────────────────
    using_file_output = env_bool("OUTPUT_TO_FILE", False)
    mongo_uri = _get_env("MONGO_URI", "MONGODB_URI")
    mongo_db = _get_env("MONGO_DB", "MONGODB_DB")
    judge_model = os.getenv("JUDGE_MODEL")
    judge_backend = os.getenv("JUDGE_BACKEND", "ollama").strip().lower()
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    required: dict[str, str | None] = {"JUDGE_MODEL": judge_model}
    if not using_file_output:
        required["MONGO_URI"] = mongo_uri
        required["MONGO_DB"] = mongo_db

    missing = [name for name, value in required.items() if not value]

    if judge_backend == "openrouter" and not openrouter_key:
        missing.append("OPENROUTER_API_KEY")

    if judge_backend not in {"ollama", "openrouter"}:
        logger.error(
            "preflight failed: unknown JUDGE_BACKEND",
            extra={
                "stage": "preflight",
                "outcome": "error",
                "error_message": f"JUDGE_BACKEND={judge_backend!r} is not supported. "
                                 "Use 'ollama' or 'openrouter'.",
            },
        )
        ok = False

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

    # ── Database connectivity (authoritative ping — store skips its own) ─────
    if not using_file_output and mongo_uri and mongo_db:
        try:
            db_ping(mongo_uri)
        except Exception as exc:  # pragma: no cover - depends on env
            logger.error(
                "preflight failed: database ping",
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
