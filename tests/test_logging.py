"""Logging security tests — secrets must never reach the output."""

from __future__ import annotations

import logging

from app.core.logging import SecretRedactionFilter

TOKEN = "123456:SUPER-SECRET-TEST-TOKEN"


def _make_record(message: str, exc: BaseException | None = None) -> logging.LogRecord:
    return logging.LogRecord(
        name="bot.test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg=message,
        args=None,
        exc_info=(type(exc), exc, exc.__traceback__) if exc else None,
    )


def test_filter_redacts_secrets_in_message():
    record = _make_record(f"Connection failed using {TOKEN}")

    SecretRedactionFilter([TOKEN]).filter(record)

    formatted = record.getMessage()
    assert TOKEN not in formatted
    assert "***REDACTED***" in formatted


def test_filter_redacts_secrets_in_traceback():
    """PTB's InvalidToken embeds the token inside the exception text."""
    try:
        raise RuntimeError(f"The token `{TOKEN}` was rejected by the server.")
    except RuntimeError as exc:
        record = _make_record("Startup failed", exc=exc)

    SecretRedactionFilter([TOKEN]).filter(record)

    assert record.exc_info is None  # replaced by pre-formatted, redacted text
    assert record.exc_text is not None
    assert TOKEN not in record.exc_text


def test_formatted_output_contains_no_secret():
    try:
        raise RuntimeError(f"The token `{TOKEN}` was rejected by the server.")
    except RuntimeError as exc:
        record = _make_record("Startup failed", exc=exc)

    SecretRedactionFilter([TOKEN]).filter(record)

    assert TOKEN not in logging.Formatter().format(record)


def test_filter_is_passthrough_without_secrets():
    record = _make_record("Nothing sensitive here")

    assert SecretRedactionFilter([]).filter(record) is True
    assert record.getMessage() == "Nothing sensitive here"
