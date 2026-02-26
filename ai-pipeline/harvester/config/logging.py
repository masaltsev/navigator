"""
Structured logging configuration for Harvester.

Uses structlog for machine-readable (JSON) and human-readable output.
All modules should use `get_logger(__name__)` from this module instead
of stdlib `logging.getLogger`.

Configuration:
  HARVESTER_LOG_FORMAT: "json" (default in production) or "console" (dev)
  HARVESTER_LOG_LEVEL: "INFO" (default), "DEBUG", "WARNING", etc.
"""

import logging
import sys

import structlog


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a bound structlog logger. Drop-in replacement for logging.getLogger."""
    return structlog.get_logger(name)


def configure_logging(
    log_format: str | None = None,
    log_level: str | None = None,
) -> None:
    """
    Configure structlog + stdlib logging for the entire process.

    Should be called once at process startup (CLI entrypoint, Celery worker,
    or API server).

    Args:
        log_format: "json" for machine-readable, "console" for human-readable.
                    Defaults to HARVESTER_LOG_FORMAT env var or "console".
        log_level: Logging level string. Defaults to HARVESTER_LOG_LEVEL or "INFO".
    """
    from config.settings import get_settings

    _s = get_settings()
    fmt = log_format or _s.harvester_log_format
    level = log_level or _s.harvester_log_level
    level_int = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if fmt == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer(
            ensure_ascii=False,
        )
    else:
        renderer = structlog.dev.ConsoleRenderer(
            colors=sys.stderr.isatty(),
        )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level_int,
        force=True,
    )

    structlog.stdlib.recreate_defaults(log_level=level_int)

    for noisy in ("httpx", "httpcore", "crawl4ai", "playwright", "urllib3", "openai"):
        logging.getLogger(noisy).setLevel(max(level_int, logging.WARNING))
