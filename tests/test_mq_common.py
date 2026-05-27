import logging

import pytest

from app.queue.mq_common import common_message_parser


def test_common_message_parser_valid_json():
    """
    Test that a valid JSON message is parsed correctly.
    """
    valid_json_string = '{"key": "value"}'
    expected_dict = {"key": "value"}
    assert common_message_parser(valid_json_string) == expected_dict


@pytest.mark.parametrize(
    "empty_input",
    [
        "",
        None,
        b"",
    ],
)
def test_common_message_parser_empty_message(empty_input, caplog):
    """
    Test that an empty or None message is handled gracefully and logged as a warning.
    """
    with caplog.at_level(logging.WARNING):
        assert common_message_parser(empty_input) is None
        assert "Received empty message from message queue, skipping." in caplog.text


def test_common_message_parser_invalid_json(caplog):
    """
    Test that an invalid JSON message is handled gracefully and logged as an error.
    """
    invalid_json_string = '{"key": "value"'
    with caplog.at_level(logging.ERROR):
        assert common_message_parser(invalid_json_string) is None
        assert "Unable to parse json message from message queue" in caplog.text
        # check that the invalid message is included in the log extra
        assert invalid_json_string in caplog.text


def test_common_message_parser_valid_unicode():
    """
    Test that a message with valid unicode characters is parsed correctly.
    This is to ensure that the comment about unicode in the source is still valid.
    """
    # This is a valid json, but contains a character that might cause issues in some systems
    # The function itself doesn't do anything special with unicode, it relies on json.loads
    # which should handle it fine.
    unicode_string = '{"key":"\\ud83d\\ude00"}'  # Grinning face emoji
    parsed = common_message_parser(unicode_string)
    assert parsed == {"key": "😀"}
