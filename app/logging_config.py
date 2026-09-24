"""Structured, privacy-conscious logging.

- Log records are emitted as single-line JSON (OpenTelemetry-friendly field names).
- Email addresses are masked in every message and extra field.
- The correlation ID is attached automatically from a context variable.
"""

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")

_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
}


def mask_email(value: str) -> str:
    """Mask email addresses: 'maya.klein@example.test' -> 'm***@example.test'."""
    return EMAIL_PATTERN.sub(r"\1***@\2", value)


def _mask(value: Any) -> Any:
    if isinstance(value, str):
        return mask_email(value)
    if isinstance(value, dict):
        return {k: _mask(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_mask(v) for v in value]
    return value


class PiiMaskingFilter(logging.Filter):
    """Masks emails in the rendered message and extras; injects correlation ID."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_email(record.getMessage())
        record.args = None
        for key, value in list(record.__dict__.items()):
            if key not in _STANDARD_ATTRS:
                record.__dict__[key] = _mask(value)
        if not hasattr(record, "correlation_id"):
            record.correlation_id = correlation_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(PiiMaskingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, PiiMaskingFilter) for f in logger.filters):
        logger.addFilter(PiiMaskingFilter())
    return logger
