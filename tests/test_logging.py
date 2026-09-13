"""Unit tests for the Loguru logging configuration and InterceptHandler."""

import json
import logging
from typing import Any

import pytest
from app.core.config import settings
from app.core.logging import (
    LOGGERS_TO_INTERCEPT,
    InterceptHandler,
    format_record,
    setup_logging,
)
from loguru import logger


@pytest.fixture(autouse=True)
def reset_logging_state():
    """Reset Loguru and stdlib logging state after each test."""
    yield
    logger.remove()
    logging.root.handlers = []


def test_setup_logging_clears_handlers_and_adds_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure setup_logging clears existing handlers and attaches a new stdout sink."""
    dummy_sink_called = False

    def dummy_sink(_message: Any) -> None:
        nonlocal dummy_sink_called
        dummy_sink_called = True

    logger.add(dummy_sink)

    monkeypatch.setattr(settings, "environment", "development")
    setup_logging()

    logger.info("Test message")
    assert not dummy_sink_called


def test_setup_logging_production_json(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify production environment outputs serialized JSON logs."""
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "log_level", "INFO")
    setup_logging()

    logger.info("production message", job_id="test-job-42")

    captured = capsys.readouterr()
    assert captured.out.strip() != ""
    log_data = json.loads(captured.out.strip().splitlines()[-1])

    assert log_data["record"]["message"] == "production message"
    assert log_data["record"]["level"]["name"] == "INFO"
    assert log_data["record"]["extra"].get("job_id") == "test-job-42"


def test_setup_logging_development_format(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify development environment outputs human-readable console format."""
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "log_level", "DEBUG")
    setup_logging()

    logger.debug("development message")

    captured = capsys.readouterr()
    output = captured.out.strip()
    assert "DEBUG" in output
    assert "development message" in output


def test_format_record_templates() -> None:
    """Verify format_record produces correct templates based on extra and exception."""
    base_record: dict[str, Any] = {"extra": {}, "exception": None}
    fmt_base = format_record(base_record)
    assert "{message}" in fmt_base
    assert "{extra}" not in fmt_base
    assert "{exception}" not in fmt_base

    extra_record: dict[str, Any] = {"extra": {"request_id": "abc"}, "exception": None}
    fmt_extra = format_record(extra_record)
    assert "{extra}" in fmt_extra
    assert "{exception}" not in fmt_extra

    exc_record: dict[str, Any] = {"extra": {}, "exception": ("type", "value", "traceback")}
    fmt_exc = format_record(exc_record)
    assert "{exception}" in fmt_exc


def test_intercept_handler_forwards_standard_logging(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify standard library logger logs are intercepted and forwarded to Loguru."""
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "log_level", "INFO")
    setup_logging()

    std_logger = logging.getLogger("test_generic_logger")
    std_logger.info("message from stdlib logger")

    captured = capsys.readouterr()
    assert "message from stdlib logger" in captured.out
    assert "INFO" in captured.out


def test_intercept_handler_forwards_intercepted_loggers(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify all designated third-party loggers are configured with InterceptHandler."""
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "log_level", "INFO")
    setup_logging()

    for logger_name in LOGGERS_TO_INTERCEPT:
        target_logger = logging.getLogger(logger_name)
        assert len(target_logger.handlers) == 1
        assert isinstance(target_logger.handlers[0], InterceptHandler)
        assert target_logger.propagate is False

        target_logger.info(f"message from {logger_name}")

    captured = capsys.readouterr()
    for logger_name in LOGGERS_TO_INTERCEPT:
        assert f"message from {logger_name}" in captured.out


def test_intercept_handler_unknown_level(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify InterceptHandler handles unknown logging levels gracefully."""
    monkeypatch.setattr(settings, "environment", "development")
    setup_logging()

    handler = InterceptHandler()
    record = logging.LogRecord(
        name="custom_logger",
        level=25,
        pathname=__file__,
        lineno=100,
        msg="message with unknown level",
        args=(),
        exc_info=None,
    )
    record.levelname = "UNKNOWN_LEVEL"

    handler.emit(record)

    captured = capsys.readouterr()
    assert "message with unknown level" in captured.out


def test_intercept_handler_no_frame(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify InterceptHandler gracefully handles scenarios where currentframe is None."""
    monkeypatch.setattr(settings, "environment", "development")
    setup_logging()

    monkeypatch.setattr(logging, "currentframe", lambda: None)

    std_logger = logging.getLogger("no_frame_logger")
    std_logger.info("message without frame")

    captured = capsys.readouterr()
    assert "message without frame" in captured.out
