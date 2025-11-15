from collections.abc import Generator

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from iqe_host_inventory import ApplicationHostInventory


@pytest.fixture(scope="session")
def inventory_db_engine(host_inventory: ApplicationHostInventory) -> Engine:
    return host_inventory.database.make_engine()


@pytest.fixture
def inventory_db_session(inventory_db_engine: Engine) -> Generator[Session, None, None]:
    """Returns an sqlalchemy session, and after the test tears down everything properly."""
    connection = inventory_db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    set_schemas = "SET SEARCH_PATH TO public,hbi"
    session.execute(set_schemas)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
