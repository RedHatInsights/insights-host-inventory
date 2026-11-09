from unittest.mock import Mock
from unittest.mock import patch

import pytest

from api.host_query_db import _order_how
from api.host_query_db import params_to_order_by


def test_asc_host_order_how():
    column = Mock()
    result = _order_how(column, "ASC")
    assert result == column.asc()


def test_desc_host_order_how():
    column = Mock()
    result = _order_how(column, "DESC")
    assert result == column.desc()


def test_error_host_order_how(subtests):
    invalid_values = (None, "asc", "desc", "BBQ")
    for invalid_value in invalid_values:
        with subtests.test(order_how=invalid_value):
            with pytest.raises(ValueError):
                _order_how(Mock(), invalid_value)


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
def test_default_is_updated_desc_host_params_to_order_by(modified_on, id_, order_how):
    actual = params_to_order_by(None, None)
    expected = (modified_on.desc.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_not_called()


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
def test_default_for_updated_is_desc_host_params_to_order_by(modified_on, id_, order_how):
    actual = params_to_order_by("updated", None)
    expected = (modified_on.desc.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_not_called()


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
def test_order_by_updated_asc_host_params_to_order_by(modified_on, id_, order_how):
    actual = params_to_order_by("updated", "ASC")
    expected = (order_how.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_called_once_with(modified_on, "ASC")


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
def test_order_by_updated_desc_host_params_to_order_by(modified_on, id_, order_how):
    actual = params_to_order_by("updated", "DESC")
    expected = (order_how.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_called_once_with(modified_on, "DESC")


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
@patch("api.host.Host.display_name")
def test_default_for_display_name_is_asc_host_params_to_order_by(display_name, modified_on, id_, order_how):
    actual = params_to_order_by("display_name")
    expected = (display_name.asc.return_value, modified_on.desc.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_not_called()


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
@patch("api.host.Host.display_name")
def test_order_by_display_name_asc_host_params_to_order_by(display_name, modified_on, id_, order_how):
    actual = params_to_order_by("display_name", "ASC")
    expected = (order_how.return_value, modified_on.desc.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_called_once_with(display_name, "ASC")


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
@patch("api.host.Host.display_name")
def test_order_by_display_name_desc_host_params_to_order_by(display_name, modified_on, id_, order_how):
    actual = params_to_order_by("display_name", "DESC")
    expected = (order_how.return_value, modified_on.desc.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_called_once_with(display_name, "DESC")


def test_order_by_bad_field_raises_error_host_params_to_order_by():
    with pytest.raises(ValueError):
        params_to_order_by(Mock(), "fqdn")


@pytest.mark.parametrize("direction", ("ASC", "DESC"))
def test_order_by_only_how_raises_error_host_params_to_order_by(direction):
    with pytest.raises(ValueError):
        params_to_order_by(order_how=direction)
