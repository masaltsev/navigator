"""Tests for config/logging.py — structlog configuration."""

import structlog
from config.logging import configure_logging, get_logger


class TestLoggingConfig:
    def test_configure_console(self):
        configure_logging(log_format="console", log_level="INFO")
        log = get_logger("test")
        assert log is not None

    def test_configure_json(self):
        configure_logging(log_format="json", log_level="DEBUG")
        log = get_logger("test_json")
        assert log is not None

    def test_get_logger_returns_bound_logger(self):
        configure_logging()
        log = get_logger("my_module")
        assert log is not None

    def test_logger_has_bind(self):
        configure_logging()
        log = get_logger("test_bind")
        bound = log.bind(url="https://example.com")
        assert bound is not None
