from datetime import datetime

import pytest
from marshmallow import ValidationError as MarshmallowValidationError
from sqlalchemy.exc import DataError
from sqlalchemy.exc import IntegrityError

from app.models import db
from app.models.system_profile_dynamic import HostDynamicSystemProfile
from app.models.system_profile_static import HostStaticSystemProfile
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import get_sample_profile_data

"""
These tests are for testing the db System Profile model classes outside of the api.
"""


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


def test_add_dynamic_profile(db_create_host):
    """
    Tests adding a HostDynamicSystemProfile record using a sample data dictionary.
    """

    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {**static_profile_data, **dynamic_profile_data}
    host = db_create_host(extra_data={"system_profile_facts": system_profile_data})
    retrieved = db.session.query(HostDynamicSystemProfile).filter_by(org_id=host.org_id, host_id=host.id).one()

    assert retrieved is not None
    for key, value in dynamic_profile_data.items():
        # We return datetime objects from the database,
        # so we need to convert them to strings for comparison
        if isinstance(getattr(retrieved, key), datetime):
            assert getattr(retrieved, key).isoformat() == value
        else:
            assert getattr(retrieved, key) == value


def test_delete_dynamic_profile(db_create_host):
    """
    Tests deleting a HostDynamicSystemProfile record from the database.
    """

    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {**static_profile_data, **dynamic_profile_data}
    host = db_create_host(extra_data={"system_profile_facts": system_profile_data})
    profile = db.session.query(HostDynamicSystemProfile).filter_by(org_id=host.org_id, host_id=host.id).one()

    db.session.delete(profile)
    db.session.commit()

    retrieved = db.session.query(HostDynamicSystemProfile).filter_by(org_id=host.org_id, host_id=host.id).one_or_none()

    assert retrieved is None


def test_update_dynamic_profile(db_create_host):
    """
    Tests updating a HostDynamicSystemProfile record in the database.
    """
    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {**static_profile_data, **dynamic_profile_data}
    host = db_create_host(extra_data={"system_profile_facts": system_profile_data})

    host.dynamic_system_profile.insights_egg_version = "2.1.4"
    db.session.commit()

    retrieved = db.session.query(HostDynamicSystemProfile).filter_by(org_id=host.org_id, host_id=host.id).one()

    assert retrieved.insights_egg_version == "2.1.4"


def test_dynamic_profile_incorrect_type(db_create_host):
    """
    Tests that creating a HostDynamicSystemProfile with incorrect data types raises an exception.
    """
    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {**static_profile_data, **dynamic_profile_data}
    system_profile_data["number_of_cpus"] = "not-a-number"
    with pytest.raises(MarshmallowValidationError):
        db_create_host(extra_data={"system_profile_facts": system_profile_data})


def test_host_system_profile_normalization_integration(db_create_host):
    """
    Integration test for the complete system profile normalization flow.
    Tests that updating a host's system profile correctly updates both JSONB and normalized tables.
    """
    # Create a host
    host = db_create_host()
    db.session.commit()

    # Verify initial state
    assert host.static_system_profile is None
    assert host.dynamic_system_profile is None
    assert host.system_profile_facts == {}

    # Update system profile with static and dynamic data
    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {**static_profile_data, **dynamic_profile_data}
    host.update_system_profile(system_profile_data)
    db.session.commit()

    # Verify normalized tables were created
    assert host.static_system_profile is not None
    assert host.dynamic_system_profile is not None

    # Verify static system profile data matches JSONB system profile data
    assert host.static_system_profile.org_id == host.org_id
    assert host.static_system_profile.host_id == host.id
    assert host.static_system_profile.arch == host.system_profile_facts["arch"]
    assert host.static_system_profile.bios_vendor == host.system_profile_facts["bios_vendor"]
    assert host.static_system_profile.cores_per_socket == host.system_profile_facts["cores_per_socket"]

    # Verify dynamic system profile data matches JSONB system profile data
    assert host.dynamic_system_profile.org_id == host.org_id
    assert host.dynamic_system_profile.host_id == host.id
    assert host.dynamic_system_profile.running_processes == host.system_profile_facts["running_processes"]
    assert host.dynamic_system_profile.network_interfaces == host.system_profile_facts["network_interfaces"]
    assert host.dynamic_system_profile.installed_packages == host.system_profile_facts["installed_packages"]

    # Test updating existing system profile
    updated_data = {
        "arch": "aarch64",  # Change static field
        "running_processes": ["systemd", "nginx"],  # Change dynamic field
    }

    host.update_system_profile(updated_data)
    db.session.commit()

    # Verify updates
    assert host.system_profile_facts["arch"] == "aarch64"
    assert host.system_profile_facts["running_processes"] == ["systemd", "nginx"]
    assert host.static_system_profile.arch == "aarch64"
    assert host.dynamic_system_profile.running_processes == ["systemd", "nginx"]


def test_create_host_with_workloads_in_top_level(db_create_host):
    """
    Tests creating a host with workloads in the top level of the system profile.
    """
    workloads_data = {
        "ansible": {
            "controller_version": "4.5.6",
            "hub_version": "4.5.6",
            "catalog_worker_version": "1.2.3",
            "sso_version": "7.8.9",
        },
        "crowdstrike": {
            "falcon_aid": "44e3b7d20b434a2bb2815d9808fa3a8b",
            "falcon_backend": "kernel",
            "falcon_version": "7.14.16703.0",
        },
        "ibm_db2": {"is_running": True},
        "intersystems": {
            "is_intersystems": True,
            "running_instances": [
                {"name": "HEALTH_PROD", "version": "2023.1.0.215.0", "path": "/opt/intersystems/iris/bin"}
            ],
        },
        "mssql": {"version": "15.2.0"},
        "oracle_db": {"is_running": False},
        "rhel_ai": {
            "variant": "RHEL AI",
            "rhel_ai_version_id": "v1.1.3",
            "gpu_models": [{"name": "NVIDIA A100 80GB PCIe", "vendor": "Nvidia", "memory": "80GB", "count": 4}],
            "ai_models": ["granite-7b-redhat-lab", "granite-7b-starter"],
            "free_disk_storage": "698GB",
        },
        "sap": {
            "sap_system": True,
            "sids": ["H2O", "ABC"],
            "instance_number": "03",
            "version": "2.00.122.04.1478575636",
        },
    }

    static_profile_data, dynamic_profile_data = get_sample_profile_data()
    system_profile_data = {**static_profile_data, **dynamic_profile_data, **workloads_data}
    host = db_create_host(extra_data={"system_profile_facts": system_profile_data})
    assert host.system_profile_facts["ansible"]["controller_version"] == "4.5.6"
