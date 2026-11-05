import pytest
from sqlalchemy.exc import DataError
from sqlalchemy.exc import IntegrityError

from app.models import db
from app.models.system_profile_static import HostStaticSystemProfile
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import get_sample_profile_data


def test_create_host_without_system_profile(db_create_host):
    # Test the situation where the db/sqlalchemy sets the
    # system_profile_facts to None
    created_host = db_create_host()
    assert created_host.static_system_profile is None


def test_create_host_with_system_profile(db_create_host):
    system_profile_facts = {"number_of_cpus": 1, "owner_id": SYSTEM_IDENTITY["system"]["cn"]}

    created_host = db_create_host(SYSTEM_IDENTITY, extra_data={"system_profile_facts": system_profile_facts})

    # Verify data is stored in normalized tables
    assert created_host.static_system_profile.number_of_cpus == system_profile_facts["number_of_cpus"]
    assert str(created_host.static_system_profile.owner_id) == system_profile_facts["owner_id"]


def test_create_host_static_system_profile(db_create_host):
    """Test creating a HostStaticSystemProfile record"""
    # Create a host first

    # Create static system profile data
    system_profile_data = {
        "arch": "x86_64",
        "basearch": "x86_64",
        "bios_vendor": "Dell Inc.",
        "bios_version": "2.15.0",
        "cloud_provider": "aws",
        "cores_per_socket": 4,
        "cpu_model": "Intel(R) Xeon(R) CPU E5-2686 v4 @ 2.30GHz",
        "host_type": "edge",
        "infrastructure_type": "virtual",
        "infrastructure_vendor": "aws",
        "insights_client_version": "3.1.7",
        "is_marketplace": False,
        "katello_agent_running": False,
        "number_of_cpus": 8,
        "number_of_sockets": 2,
        "operating_system": {"name": "RHEL", "major": 9, "minor": 1},
        "os_kernel_version": "5.14.0",
        "os_release": "Red Hat Enterprise Linux 9.1",
        "satellite_managed": False,
        "system_update_method": "yum",
        "threads_per_core": 2,
    }

    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "system_profile_facts": system_profile_data,
            "display_name": "test_host_for_static_profile",
        },
    )

    db.session.commit()

    # Verify the record was created
    retrieved_profile = (
        db.session.query(HostStaticSystemProfile)
        .filter_by(org_id=created_host.org_id, host_id=created_host.id)
        .first()
    )

    assert retrieved_profile is not None
    assert retrieved_profile.org_id == created_host.org_id
    assert retrieved_profile.host_id == created_host.id
    assert retrieved_profile.arch == "x86_64"
    assert retrieved_profile.bios_vendor == "Dell Inc."
    assert retrieved_profile.cores_per_socket == 4
    assert retrieved_profile.number_of_cpus == 8
    assert retrieved_profile.operating_system == {"name": "RHEL", "major": 9, "minor": 1}


@pytest.mark.parametrize(
    "field,value",
    [
        ("cores_per_socket", -1),
        ("cores_per_socket", 2147483648),  # Max int + 1
        ("number_of_cpus", -1),
        ("number_of_cpus", 2147483648),
        ("number_of_sockets", -1),
        ("number_of_sockets", 2147483648),
        ("threads_per_core", -1),
        ("threads_per_core", 2147483648),
    ],
)
def test_host_static_system_profile_check_constraints(db_create_host, field, value):
    """Test check constraints on integer fields"""
    db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            "display_name": "test_host_constraints",
        },
    )

    data = {
        field: value,
    }

    static_profile = HostStaticSystemProfile(**data)
    db.session.add(static_profile)
    if value == -1:
        with pytest.raises(IntegrityError):
            db.session.commit()
    else:
        with pytest.raises(DataError):
            db.session.commit()


def test_update_host_static_system_profile(db_create_host):
    """Test updating a HostStaticSystemProfile record"""

    # Create initial static system profile
    initial_data = {
        "arch": "x86_64",
        "number_of_cpus": 4,
        "host_type": "edge",
        "system_update_method": "yum",
    }

    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "system_profile_facts": initial_data,
            "display_name": "test_host_update",
        },
    )

    # Update the record
    created_host.static_system_profile.arch = "aarch64"
    created_host.static_system_profile.number_of_cpus = 8
    created_host.static_system_profile.host_type = "host"
    created_host.static_system_profile.system_update_method = "dnf"
    created_host.static_system_profile.bios_vendor = "Updated Vendor"
    db.session.commit()

    # Verify the updates
    retrieved_profile = (
        db.session.query(HostStaticSystemProfile)
        .filter_by(org_id=created_host.org_id, host_id=created_host.id)
        .first()
    )

    assert retrieved_profile.arch == "aarch64"
    assert retrieved_profile.number_of_cpus == 8
    assert retrieved_profile.host_type == "host"
    assert retrieved_profile.system_update_method == "dnf"
    assert retrieved_profile.bios_vendor == "Updated Vendor"


def test_delete_host_static_system_profile(db_create_host):
    """Test deleting a HostStaticSystemProfile record"""

    static_profile_data = {
        "arch": "x86_64",
        "number_of_cpus": 4,
    }

    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "system_profile_facts": static_profile_data,
            "display_name": "test_host_delete",
        },
    )

    db.session.commit()

    # Verify it exists
    retrieved_profile = (
        db.session.query(HostStaticSystemProfile)
        .filter_by(org_id=created_host.org_id, host_id=created_host.id)
        .first()
    )
    assert retrieved_profile is not None

    # Delete the record
    db.session.delete(created_host)
    db.session.commit()

    # Verify it's gone
    retrieved_profile = (
        db.session.query(HostStaticSystemProfile)
        .filter_by(org_id=created_host.org_id, host_id=created_host.id)
        .first()
    )
    assert retrieved_profile is None


def test_host_static_system_profile_complex_data_types(db_create_host):
    """Test HostStaticSystemProfile with complex JSONB and array data types"""

    # Create static system profile with complex data
    complex_data = {
        "operating_system": {
            "name": "Red Hat Enterprise Linux Server",
            "major": 9,
            "minor": 1,
        },
        "bootc_status": {
            "booted": {
                "image": "quay.io/example/bootc:latest",
                "incompatible": False,
                "pinned": False,
            },
            "rollback": {
                "image": "quay.io/example/bootc:previous",
                "incompatible": False,
                "pinned": True,
            },
        },
        "disk_devices": [
            {
                "device": "/dev/sda",
                "label": "disk1",
                "mount_point": "/",
                "type": "disk",
            },
            {
                "device": "/dev/sdb",
                "label": "disk2",
                "mount_point": "/home",
                "type": "disk",
            },
        ],
        "enabled_services": ["sshd", "chronyd", "NetworkManager"],
        "gpg_pubkeys": ["key1", "key2", "key3"],
        "public_dns": ["8.8.8.8", "8.8.4.4"],
        "public_ipv4_addresses": ["203.0.113.1", "203.0.113.2"],
        "conversions": {"activity": "Conversion completed successfully"},
        "rhsm": {
            "version": "1.29.26",
            "environment_ids": ["262e621d10ae4475ab5732b39a9160b2"],
        },
        "yum_repos": [
            {
                "id": "rhel-9-appstream-rpms",
                "name": "Red Hat Enterprise Linux 9 - AppStream",
                "enabled": True,
            }
        ],
    }

    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "system_profile_facts": complex_data,
            "display_name": "test_host_complex_data",
        },
    )

    # Verify the complex data was stored correctly
    retrieved_profile = (
        db.session.query(HostStaticSystemProfile)
        .filter_by(org_id=created_host.org_id, host_id=created_host.id)
        .first()
    )

    assert retrieved_profile.operating_system["name"] == "Red Hat Enterprise Linux Server"
    assert retrieved_profile.operating_system["major"] == 9
    assert retrieved_profile.bootc_status["booted"]["image"] == "quay.io/example/bootc:latest"
    assert len(retrieved_profile.disk_devices) == 2
    assert retrieved_profile.disk_devices[0]["device"] == "/dev/sda"
    assert "sshd" in retrieved_profile.enabled_services
    assert "8.8.8.8" in retrieved_profile.public_dns
    assert retrieved_profile.rhsm["version"] == "1.29.26"
    assert len(retrieved_profile.yum_repos) == 1
    assert retrieved_profile.yum_repos[0]["id"] == "rhel-9-appstream-rpms"


def test_host_system_profile_normalization_integration(db_create_host):
    """
    Integration test for the complete system profile normalization flow.
    Tests that updating a host's system profile correctly updates normalized tables.
    """
    # Create a host
    host = db_create_host()
    db.session.commit()

    # Verify initial state
    assert host.static_system_profile is None
    assert host.dynamic_system_profile is None

    # Update system profile with static and dynamic data
    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {**static_profile_data, **dynamic_profile_data}
    host.update_system_profile(system_profile_data)
    db.session.commit()

    # Verify normalized tables were created
    assert host.static_system_profile is not None
    assert host.dynamic_system_profile is not None

    # Verify static system profile data matches input data
    assert host.static_system_profile.org_id == host.org_id
    assert host.static_system_profile.host_id == host.id
    assert host.static_system_profile.arch == static_profile_data["arch"]
    assert host.static_system_profile.bios_vendor == static_profile_data["bios_vendor"]
    assert host.static_system_profile.cores_per_socket == static_profile_data["cores_per_socket"]

    # Verify dynamic system profile data matches input data
    assert host.dynamic_system_profile.org_id == host.org_id
    assert host.dynamic_system_profile.host_id == host.id
    assert host.dynamic_system_profile.running_processes == dynamic_profile_data["running_processes"]
    assert host.dynamic_system_profile.network_interfaces == dynamic_profile_data["network_interfaces"]
    assert host.dynamic_system_profile.installed_packages == dynamic_profile_data["installed_packages"]

    # Test updating existing system profile
    updated_data = {
        "arch": "aarch64",  # Change static field
        "running_processes": ["systemd", "nginx"],  # Change dynamic field
    }

    host.update_system_profile(updated_data)
    db.session.commit()

    # Verify updates in normalized tables
    assert host.static_system_profile.arch == "aarch64"
    assert host.dynamic_system_profile.running_processes == ["systemd", "nginx"]
