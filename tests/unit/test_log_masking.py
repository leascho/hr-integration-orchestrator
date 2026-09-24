import json
import logging

from app.logging_config import JsonFormatter, PiiMaskingFilter, get_logger, mask_email


def test_mask_email():
    assert mask_email("maya.klein@example.test") == "m***@example.test"
    assert mask_email("contact a.b@x.example.test now") == "contact a***@x.example.test now"
    assert mask_email("no email here") == "no email here"


def test_logger_masks_message_args_and_extras(caplog):
    logger = get_logger("tests.masking")
    with caplog.at_level(logging.INFO):
        logger.info(
            "Provisioning %s",
            "maya.klein@example.test",
            extra={"recipient": "maya.klein@example.test", "nested": {"e": "x.y@example.test"}},
        )
    record = caplog.records[-1]
    assert "maya.klein@example.test" not in caplog.text
    assert record.getMessage() == "Provisioning m***@example.test"
    assert record.recipient == "m***@example.test"
    assert record.nested == {"e": "x***@example.test"}


def test_json_formatter_output_is_masked_and_structured():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "to %s", ("a.b@example.test",), None)
    record.integration_run_id = "run-1"
    PiiMaskingFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "to a***@example.test"
    assert payload["integration_run_id"] == "run-1"
    assert payload["severity"] == "INFO"
