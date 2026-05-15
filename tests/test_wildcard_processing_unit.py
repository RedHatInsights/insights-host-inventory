"""
Unit tests for the _process_wildcard_value function to verify URL encoding handling.
"""

from api.filtering.db_custom_filters import _process_wildcard_value


def test_process_wildcard_value_url_encoded_asterisk():
    """Test that URL-encoded asterisk (%2A) becomes literal asterisk."""
    result = _process_wildcard_value("abc%2A123")
    assert result == "abc*123"


def test_process_wildcard_value_actual_asterisk():
    """Test that actual asterisk (*) becomes SQL wildcard (%)."""
    result = _process_wildcard_value("abc*123")
    assert result == "abc%123"


def test_process_wildcard_value_mixed_encoding():
    """Test mixed URL encoding and wildcards."""
    result = _process_wildcard_value("test%2Avalue*more")
    assert result == "test*value%more"


def test_process_wildcard_value_backslash_encoding():
    """Test URL-encoded backslash handling."""
    result = _process_wildcard_value("test%2Avalue%5Cmore")
    assert result == "test*value\\more"


def test_process_wildcard_value_complex_case():
    """Test the complex case from the issue."""
    result = _process_wildcard_value("test1%2Atest2%5Ctest3")
    assert result == "test1*test2\\test3"


def test_process_wildcard_value_multiple_wildcards():
    """Test multiple wildcards and encoded characters."""
    result = _process_wildcard_value("*start%2Amiddle*end%26more")
    assert result == "%start*middle%end&more"


def test_process_wildcard_value_no_encoding():
    """Test string with no URL encoding or wildcards."""
    result = _process_wildcard_value("simple_string")
    assert result == "simple_string"


def test_process_wildcard_value_only_wildcards():
    """Test string with only wildcards."""
    result = _process_wildcard_value("***")
    assert result == "%%%"


def test_process_wildcard_value_only_encoded():
    """Test string with only URL-encoded characters."""
    result = _process_wildcard_value("%2A%5C%26")
    assert result == "*\\&"


def test_process_wildcard_value_empty_string():
    """Test empty string."""
    result = _process_wildcard_value("")
    assert result == ""


def test_process_wildcard_value_multiple_encoded_asterisks():
    """Test multiple URL-encoded asterisks."""
    result = _process_wildcard_value("start%2Amiddle%2Aend")
    assert result == "start*middle*end"


def test_process_wildcard_value_mixed_asterisks_and_encoded():
    """Test mix of actual and URL-encoded asterisks."""
    result = _process_wildcard_value("*%2A*%2A*")
    assert result == "%*%*%"


def test_process_wildcard_value_no_url_encoded_asterisks():
    """Test that when there are no %2A, normal URL decoding and wildcard processing happens."""
    result = _process_wildcard_value("test%26value*more")
    assert result == "test&value%more"
