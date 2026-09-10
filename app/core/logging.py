"""Centralized Loguru logging configuration and standard library intercept handler."""

import logging
import sys
from typing import Any

from loguru import logger

from app.core.config import settings

LOGGERS_TO_INTERCEPT: tuple[str, ...] = (
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "fastapi",
    "arq",
    "sqlalchemy",
)


def format_record(record: dict[str, Any]) -> str:
    """Format log record for human-readable development console output."""
    format_str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    if record.get("extra"):
        format_str += " | <blue>{extra}</blue>"
    format_str += "\n"
    if record.get("exception") is not None:
        format_str += "{exception}\n"
    return format_str


class InterceptHandler(logging.Handler):
    """Standard library logging handler forwarding records to Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        """Forward a standard library LogRecord to Loguru with correct depth and level."""
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = logging.currentframe()
        depth = 0
        while frame:
            filename = frame.f_code.co_filename
            is_logging = filename == logging.__file__
            is_frozen = "importlib" in filename and "_bootstrap" in filename
            if depth > 0 and not (is_logging or is_frozen):
                break
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging() -> None:
    """Configure Loguru sinks and route standard library loggers through InterceptHandler."""
    logger.remove()

    is_production = settings.environment.lower() == "production"
    log_level = settings.log_level.upper()

    if is_production:
        logger.add(
            sys.stdout,
            level=log_level,
            serialize=True,
        )
    else:
        logger.add(
            sys.stdout,
            level=log_level,
            format=format_record,
            colorize=True,
        )

    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(log_level)

    for logger_name in LOGGERS_TO_INTERCEPT:
        lib_logger = logging.getLogger(logger_name)
        lib_logger.handlers = [InterceptHandler()]
        lib_logger.setLevel(log_level)
        lib_logger.propagate = False
