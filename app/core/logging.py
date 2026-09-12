"""Central logging setup.

* Console + rotating file output.
* A safety net that redacts known secrets from every log record — including
  formatted tracebacks (e.g. PTB's ``InvalidToken`` error embeds the token).
* Noisy third-party loggers (``httpx`` in particular — its request lines
  contain the bot API URL, which includes the token) are quietened down.
"""

from __future__ import annotations

import logging
import traceback
from logging.handlers import RotatingFileHandler
from typing import Iterable

from app.core.config import PROJECT_ROOT

LOG_DIR: Path = PROJECT_ROOT / "logs"
LOG_FILE: Path = LOG_DIR / "bot.log"

_QUIET_LOGGERS = ("httpx", "httpcore", "apscheduler")

_REDACTED = "***REDACTED***"


class SecretRedactionFilter(logging.Filter):
    """Replace known secrets with a placeholder in every log record.

    Covers both the formatted message *and* the attached traceback text,
    which is where PTB leaks the token on authentication failures.
    """

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True

        original_message = record.getMessage()
        redacted_message = self._redact(original_message)
        if redacted_message != original_message:
            record.msg = redacted_message
            record.args = None

        if record.exc_info is not None:
            # Pre-format the traceback ourselves so we can redact it; the
            # formatter then uses ``exc_text`` instead of ``exc_info``.
            if record.exc_text is None:
                record.exc_text = "".join(
                    traceback.format_exception(*record.exc_info)
                )
            record.exc_info = None
        if record.exc_text:
            record.exc_text = self._redact(record.exc_text)

        return True

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, _REDACTED)
        return text


def setup_logging(level: str = "INFO", secrets: Iterable[str] = ()) -> None:
    """Configure the root logger for the whole application (idempotent)."""
    root = logging.getLogger()
    if root.handlers:  # Already configured (e.g. double import in tests).
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    secret_filter = SecretRedactionFilter(secrets)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(secret_filter)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(secret_filter)

    root.setLevel(level.upper())
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Never let HTTP request lines (they embed the bot token in the URL) through.
    for logger_name in _QUIET_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
