"""
Structured logging setup using Loguru.

Call ``setup_logging()`` once at application startup (inside the lifespan
handler). After that, simply ``from loguru import logger`` anywhere and
log normally — all sinks will already be configured.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from app.core.config import settings


def _json_serializer(message: str) -> str:  # pragma: no cover — loguru sink
    """Loguru ``serialize=True`` handles JSON internally; this is a fallback
    formatter when JSON mode is off but we still want structured-ish output."""
    record = message.record
    return (
        f"{record['time']:YYYY-MM-DD HH:mm:ss.SSS} | "
        f"{record['level']:<8} | "
        f"{record['name']}:{record['function']}:{record['line']} | "
        f"{record['message']}\n"
    )


# ---------------------------------------------------------------------------
# Per-module log level overrides.  Noisy libraries get silenced to WARNING
# while our own critical paths stay at DEBUG in development.
# ---------------------------------------------------------------------------
_MODULE_LEVELS: dict[str, str] = {
    "app.services.market_data": "DEBUG",
    "app.services.scanner": "DEBUG",
    "app.services.executor": "DEBUG",
    "app.services.risk": "DEBUG",
    "app.api": "INFO",
    "app.db": "WARNING",
    "uvicorn.access": "WARNING",
    "uvicorn.error": "INFO",
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "sqlalchemy.engine": "WARNING",
}


def _level_filter(module: str):
    """Return a loguru filter function that only lets through records at or
    above the configured level for *module*."""
    import logging

    threshold = logging.getLevelName(_MODULE_LEVELS.get(module, settings.logging.level))

    def _filter(record: dict) -> bool:
        return record["level"].no >= threshold

    return _filter


def setup_logging() -> None:
    """Remove default Loguru handler and install production sinks."""

    # Wipe any previously-installed handlers (safe to call multiple times).
    logger.remove()

    log_dir = Path(settings.logging.dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    use_json = settings.logging.json_format
    common_sink_kwargs: dict = dict(
        rotation=settings.logging.rotation,
        retention=settings.logging.retention,
        compression=settings.logging.compression,
        enqueue=True,  # thread-safe, non-blocking
    )

    # ---- stderr (for local dev / Docker stdout) ----------------------------
    logger.add(
        sys.stderr,
        level=settings.logging.level,
        serialize=use_json,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level:<8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
        if not use_json
        else "{message}",
        colorize=not use_json,
    )

    # ---- Main application log ----------------------------------------------
    logger.add(
        str(log_dir / settings.logging.app_file),
        level=settings.logging.level,
        serialize=use_json,
        **common_sink_kwargs,
    )

    # ---- Trade-specific log (only INFO+ from executor/scanner) -------------
    logger.add(
        str(log_dir / settings.logging.trade_file),
        level="INFO",
        serialize=use_json,
        filter=lambda record: record["name"].startswith(
            ("app.services.executor", "app.services.scanner", "app.services.risk")
        ),
        **common_sink_kwargs,
    )

    # ---- Error-only log ----------------------------------------------------
    logger.add(
        str(log_dir / settings.logging.error_file),
        level="ERROR",
        serialize=use_json,
        backtrace=True,
        diagnose=True,
        **common_sink_kwargs,
    )

    # Apply per-module level overrides by binding extra context.
    for module, level in _MODULE_LEVELS.items():
        logger.bind(module=module).level = level  # type: ignore[attr-defined]

    logger.info(
        "Logging initialised",
        json_mode=use_json,
        level=settings.logging.level,
        log_dir=str(log_dir),
    )
