import pytest

from api.filtering.filtering_common import escape_ilike_value


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("hello", "hello"),
        ("hello%world", "hello\\%world"),
        ("hello_world", "hello\\_world"),
        ("hello\\world", "hello\\\\world"),
        ("hello*world", "hello%world"),
        ("hello\\%_*world", "hello\\\\\\%\\_%world"),
        (123, 123),
        (None, None),
    ],
)
def test_escape_ilike_value(input_val, expected):
    assert escape_ilike_value(input_val) == expected
