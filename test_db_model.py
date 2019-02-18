import pytest

from app import create_app, db
from app.models import Host



@pytest.fixture
def app():
    """
    Temporarily rename the host table while the tests run.  This is done
    to make dropping the table at the end of the tests a bit safer.
    """
    temp_table_name_suffix = "__unit_tests__"
    if temp_table_name_suffix not in Host.__table__.name:
        Host.__table__.name = Host.__table__.name + temp_table_name_suffix
    if temp_table_name_suffix not in Host.__table__.fullname:
        Host.__table__.fullname = Host.__table__.fullname + temp_table_name_suffix

    app = create_app(config_name="testing")

    # binds the app to the current context
    with app.app_context() as ctx:
        # create all tables
        db.create_all()
        ctx.push()
        yield app
        ctx.pop

        db.session.remove()
        db.drop_all()

def _create_host(fqdn=None, display_name=None):
    canonical_facts = {}
    if fqdn:
        canonical_facts = {'fqdn': fqdn}
    host = Host(canonical_facts, display_name=display_name, account="00102")
    db.session.add(host)
    db.session.commit()
    return host


def test_update_existing_host_fix_display_name_using_existing_fqdn(app):
    expected_fqdn = 'host1.domain1.com'
    existing_host = _create_host(fqdn=expected_fqdn, display_name=None)

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    update_host = Host({}, display_name='')
    existing_host.update(update_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_fix_display_name_using_input_fqdn(app):
    # Create an "existing" host
    fqdn = 'host1.domain1.com'
    existing_host = _create_host(fqdn=fqdn, display_name=None)

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    expected_fqdn = "different.domain1.com"
    update_host = Host({"fqdn": expected_fqdn}, display_name='')
    existing_host.update(update_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_fix_display_name_using_id(app):
    # Create an "existing" host
    existing_host = _create_host(fqdn=None, display_name=None)

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    update_host = Host({}, display_name='')
    existing_host.update(update_host)

    assert existing_host.display_name == existing_host.id
