import httpx
import pytest

from app.domain.errors import (
    ErrorCategory,
    IntegrationError,
    classify_exception,
    classify_status_code,
)


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (400, ErrorCategory.VALIDATION_ERROR),
        (401, ErrorCategory.AUTHENTICATION_ERROR),
        (403, ErrorCategory.AUTHENTICATION_ERROR),
        (404, ErrorCategory.PERMANENT_TECHNICAL_ERROR),
        (408, ErrorCategory.TRANSIENT_TECHNICAL_ERROR),
        (409, ErrorCategory.BUSINESS_RULE_ERROR),
        (422, ErrorCategory.VALIDATION_ERROR),
        (429, ErrorCategory.TRANSIENT_TECHNICAL_ERROR),
        (500, ErrorCategory.PERMANENT_TECHNICAL_ERROR),
        (502, ErrorCategory.TRANSIENT_TECHNICAL_ERROR),
        (503, ErrorCategory.TRANSIENT_TECHNICAL_ERROR),
        (504, ErrorCategory.TRANSIENT_TECHNICAL_ERROR),
    ],
)
def test_status_code_classification(status_code, expected):
    assert classify_status_code(status_code) == expected


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://svc.invalid/x")
    return httpx.HTTPStatusError("err", request=request, response=httpx.Response(code))


def test_timeout_is_transient_and_retryable():
    err = classify_exception(httpx.ReadTimeout("slow"), "Identity")
    assert err.category == ErrorCategory.TRANSIENT_TECHNICAL_ERROR
    assert err.retryable


def test_connect_error_is_dependency_unavailable_and_retryable():
    err = classify_exception(httpx.ConnectError("refused"), "Identity")
    assert err.category == ErrorCategory.DEPENDENCY_UNAVAILABLE
    assert err.retryable


@pytest.mark.parametrize("code", [400, 401, 409, 500])
def test_non_transient_http_errors_are_not_retryable(code):
    assert not classify_exception(_status_error(code), "Identity").retryable


def test_unknown_exception_is_permanent_and_message_is_safe():
    err = classify_exception(RuntimeError("secret internal detail maya@example.test"), "Identity")
    assert err.category == ErrorCategory.PERMANENT_TECHNICAL_ERROR
    assert "secret" not in err.safe_message
    assert "@" not in err.safe_message


def test_integration_error_passes_through():
    original = IntegrationError(ErrorCategory.BUSINESS_RULE_ERROR, "rule")
    assert classify_exception(original, "x") is original
