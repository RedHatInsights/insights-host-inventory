from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from tests.helpers.sql_dump import SQLDump
from tests.helpers.sql_dump import dumps_sql


@pytest.fixture(autouse=True)
def mock_sqlevent():
    with patch("tests.helpers.sql_dump.sqlevent") as mock_event:
        yield mock_event


@pytest.fixture(autouse=True)
def mock_db_engine():
    with patch("tests.helpers.sql_dump.db") as mock_db:
        mock_db.engine = MagicMock()
        yield mock_db


def test_sqldump_custom_dump_method_stored():
    """Custom dump_method is stored as self.dump_method without raising."""
    custom_method = MagicMock()
    sqld = SQLDump(dump_method=custom_method)
    assert sqld.dump_method is custom_method


def test_decorator_regular_function_raises_still_removes_listener(mock_sqlevent):
    """If the decorated regular function raises, sqlevent.remove is still called."""

    @dumps_sql
    def failing_func():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        failing_func()

    mock_sqlevent.remove.assert_called_once()


def test_decorator_generator_function_listener_active_across_yields(mock_sqlevent):
    """
    For a generator function, sqlevent.listen should be called before the first yield
    and sqlevent.remove should only be called after the generator is exhausted.
    """
    listen_call_count_during_iteration = []

    @dumps_sql
    def generating_func():
        yield 1
        yield 2
        yield 3

    gen = generating_func()

    # The listener should not have been registered yet (generator not started)
    assert mock_sqlevent.listen.call_count == 0

    for _item in gen:
        # During iteration, listen should have been called once and remove not yet
        listen_call_count_during_iteration.append(mock_sqlevent.listen.call_count)
        assert mock_sqlevent.remove.call_count == 0

    # After exhaustion, remove should have been called exactly once
    assert mock_sqlevent.listen.call_count == 1
    assert mock_sqlevent.remove.call_count == 1
    # listen was active during all iterations
    assert all(count == 1 for count in listen_call_count_during_iteration)


def test_sql_dump_single_write():
    mock_write = MagicMock()
    sql_dump = SQLDump(write_method=mock_write)

    # Mock clauseelement
    mock_compiled = MagicMock()
    mock_compiled.__str__.return_value = "SELECT * FROM hosts"
    mock_compiled.params = {"id": 123}

    mock_clauseelement = MagicMock()
    mock_clauseelement.compile.return_value = mock_compiled

    # Invoke dump_sql
    sql_dump.dump_sql(None, mock_clauseelement, None, None, None)

    # Assert write_method called exactly once
    mock_write.assert_called_once()

    # Assert the single argument contains the query, parameters, and delimiters
    called_arg = mock_write.call_args[0][0]
    assert "**** QUERY:\n" in called_arg
    assert "SELECT * FROM hosts" in called_arg
    assert "**** PARAMETERS:\n" in called_arg
    assert "123" in called_arg
    assert "****************\n" in called_arg


def test_dumps_sql_decorator_single_write(mock_sqlevent):
    mock_write = MagicMock()

    @dumps_sql(write_method=mock_write)
    def dummy_test_func():
        # Retrieve the registered listener from mock_sqlevent.listen call
        assert mock_sqlevent.listen.call_count == 1
        listener = mock_sqlevent.listen.call_args[0][2]

        # Mock clauseelement
        mock_compiled = MagicMock()
        mock_compiled.__str__.return_value = "SELECT 1"
        mock_compiled.params = {}
        mock_clauseelement = MagicMock()
        mock_clauseelement.compile.return_value = mock_compiled

        # Call the listener
        listener(None, mock_clauseelement, None, None, None)

    dummy_test_func()

    # Assert write_method called exactly once
    mock_write.assert_called_once()
    called_arg = mock_write.call_args[0][0]
    assert "SELECT 1" in called_arg
