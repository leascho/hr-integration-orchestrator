"""Error taxonomy and classification rules."""

from enum import StrEnum

import httpx


class ErrorCategory(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    TRANSIENT_TECHNICAL_ERROR = "TRANSIENT_TECHNICAL_ERROR"
    PERMANENT_TECHNICAL_ERROR = "PERMANENT_TECHNICAL_ERROR"
    BUSINESS_RULE_ERROR = "BUSINESS_RULE_ERROR"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


RETRYABLE_CATEGORIES = frozenset(
    {ErrorCategory.TRANSIENT_TECHNICAL_ERROR, ErrorCategory.DEPENDENCY_UNAVAILABLE}
)

# Errors that stop the run as FAILED (the input itself must be corrected at the source).
# All other non-retryable errors, and exhausted retries, require manual review.
SOURCE_CORRECTION_CATEGORIES = frozenset(
    {ErrorCategory.VALIDATION_ERROR, ErrorCategory.BUSINESS_RULE_ERROR}
)

TRANSIENT_STATUS_CODES = frozenset({408, 425, 429, 502, 503, 504})


class IntegrationError(Exception):
    """An error with a safe, PII-free message suitable for audit records and API output."""

    def __init__(self, category: ErrorCategory, safe_message: str) -> None:
        super().__init__(safe_message)
        self.category = category
        self.safe_message = safe_message

    @property
    def retryable(self) -> bool:
        return self.category in RETRYABLE_CATEGORIES


def classify_status_code(status_code: int) -> ErrorCategory:
    if status_code in (401, 403):
        return ErrorCategory.AUTHENTICATION_ERROR
    if status_code in TRANSIENT_STATUS_CODES:
        return ErrorCategory.TRANSIENT_TECHNICAL_ERROR
    if status_code in (400, 422):
        return ErrorCategory.VALIDATION_ERROR
    if status_code == 409:
        return ErrorCategory.BUSINESS_RULE_ERROR
    return ErrorCategory.PERMANENT_TECHNICAL_ERROR


def classify_exception(exc: Exception, system: str) -> IntegrationError:
    """Translate transport/HTTP exceptions into an IntegrationError without leaking details."""
    if isinstance(exc, IntegrationError):
        return exc
    if isinstance(exc, httpx.TimeoutException):
        return IntegrationError(
            ErrorCategory.TRANSIENT_TECHNICAL_ERROR, f"{system} request timed out."
        )
    if isinstance(exc, httpx.ConnectError | httpx.NetworkError):
        return IntegrationError(ErrorCategory.DEPENDENCY_UNAVAILABLE, f"{system} is unreachable.")
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return IntegrationError(classify_status_code(code), f"{system} responded with HTTP {code}.")
    return IntegrationError(
        ErrorCategory.PERMANENT_TECHNICAL_ERROR, f"Unexpected error while calling {system}."
    )
