# from unittest import mock
from sqlalchemy.sql.expression import true
import pytest
from unittest import mock
from app.logging import get_logger
from app.models import ProviderType
from app import db
from app import threadctx
from app import UNKNOWN_REQUEST_ID_VALUE
from host_delete_duplicates import run as host_delete_duplicates_run
from host_delete_duplicates import _init_db as _init_db
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.test_utils import get_staleness_timestamps
from lib.handlers import register_shutdown
from tests.helpers.test_utils import generate_uuid
from lib.db import session_guard

logger = get_logger(__name__)


# @pytest.mark.host_delete_duplicates
def test_delete_duplicate_host(
    event_producer_mock, db_create_host, db_get_host, inventory_config,
):
    print("reunning sdas")

    # make two hosts that are the same
    canonical_facts = {
        "provider_type": ProviderType.AWS,  # Doesn't matter
        "provider_id": generate_uuid(),
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
    }
    old_host = minimal_db_host(canonical_facts = canonical_facts)
    new_host = minimal_db_host(canonical_facts = canonical_facts)

    created_old_host = db_create_host(host=old_host)
    created_new_host = db_create_host(host=new_host)

    assert created_old_host.id != created_new_host.id
    old_host_id = created_old_host.id
    assert created_old_host.canonical_facts["provider_id"] == created_new_host.canonical_facts["provider_id"]

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE

    Session = _init_db(inventory_config)
    accounts_session = Session()
    hosts_session = Session()
    misc_session = Session()


    with session_guard(accounts_session), session_guard(hosts_session), session_guard(misc_session):
        num_deleted = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            accounts_session,
            hosts_session,
            misc_session,
            event_producer_mock,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )

    print("deleted this many hosts:")
    print(num_deleted)

    # force the db session to re-fetch hosts from the database
    # necessary because the deletions took place in another session
    # the existing db.session session map is out of date
    db.session.expunge_all()

    assert num_deleted == 1
    assert db_get_host(created_new_host.id)
    assert not db_get_host(old_host_id)

# create a bunch of hosts * chunk_size
# create some duplicates of those hosts and store their IDs 
# since they were created after we should expect them to exist after
# check that the count matches initial size
# check that old dupes are gone and new ones are present
# check no other are missing
@pytest.mark.host_delete_duplicates
def test_delete_more_hosts_than_chunk_size(event_producer_mock, db_get_host, db_create_multiple_hosts, db_create_host, inventory_config):
    staleness_timestamps = get_staleness_timestamps()

    base_canonical_facts = {
        "provider_id": generate_uuid(),
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
    }

    
    chunk_size = inventory_config.script_chunk_size
    num_hosts = chunk_size * 3 + 15

    created_hosts = db_create_multiple_hosts(how_many=num_hosts)

    old_host_1 = minimal_db_host(
        stale_timestamp=staleness_timestamps["fresh"],
        reporter="some reporter", 
        canonical_facts=base_canonical_facts
    )
    new_host_1 = minimal_db_host(
        stale_timestamp=staleness_timestamps["fresh"],
        reporter="some reporter", 
        canonical_facts=base_canonical_facts
    )

    created_old_host_1 = db_create_host(host=old_host_1)
    # old_host_2 = created_hosts[chunk_size * 2 + 10]
    # old_host_3 = created_hosts[chunk_size * 3 + 10]

    created_new_host_1 = db_create_host(host=new_host_1)
    # new_host_2 = db_create_host(created_hosts[chunk_size * 2 + 10])
    # new_host_2 = db_create_host(created_hosts[chunk_size * 3 + 10])

    assert created_old_host_1.id != created_new_host_1.id

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE

    Session = _init_db(inventory_config)
    accounts_session = Session()
    hosts_session = Session()
    misc_session = Session()

    with session_guard(accounts_session), session_guard(hosts_session), session_guard(misc_session):
        host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            accounts_session,
            hosts_session,
            misc_session,
            event_producer_mock,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )

    db.session.expunge_all()
    assert db_get_host(created_new_host_1.id)
    assert not db_get_host(created_old_host_1.id)
