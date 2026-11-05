import uuid
from datetime import datetime
from datetime import timedelta

import pytest
from sqlalchemy.exc import DataError

from app.exceptions import ValidationException
from app.models import Host
from app.models import HostAppDataAdvisor
from app.models import HostAppDataCompliance
from app.models import HostAppDataMalware
from app.models import HostAppDataPatch
from app.models import HostAppDataRemediations
from app.models import HostAppDataVulnerability
from app.models import LimitedHost
from app.models import db
from app.models.system_profile_dynamic import HostDynamicSystemProfile
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_sample_profile_data
from tests.helpers.test_utils import now


def test_create_host_with_fqdn_and_display_name_as_empty_str(db_create_host):
    # Verify that the display_name is populated from the fqdn
    fqdn = "spacely_space_sprockets.orbitcity.com"

    created_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "fqdn": fqdn,
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
        },
    )

    assert created_host.display_name == fqdn


def test_create_host_with_display_name_and_fqdn_as_empty_str(db_create_host):
    # Verify that the display_name is populated from the id
    created_host = db_create_host()

    assert created_host.display_name == str(created_host.id)


def test_update_existing_host_fix_display_name_using_existing_fqdn(db_create_host):
    expected_fqdn = "host1.domain1.com"
    insights_id = generate_uuid()

    existing_host = db_create_host(
        extra_data={"fqdn": expected_fqdn, "insights_id": insights_id, "display_name": None}
    )

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    input_host = Host(
        insights_id=insights_id,
        display_name="",
        reporter="puptoo",
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(input_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_display_name_changing_fqdn(db_create_host):
    old_fqdn = "host1.domain1.com"
    new_fqdn = "host2.domain2.com"
    insights_id = generate_uuid()

    existing_host = db_create_host(extra_data={"fqdn": old_fqdn, "insights_id": insights_id, "display_name": None})

    # Set the display_name to the old FQDN
    existing_host.display_name = old_fqdn
    db.session.commit()
    assert existing_host.display_name == old_fqdn

    # Update the host
    input_host = Host(
        fqdn=new_fqdn,
        insights_id=insights_id,
        display_name="",
        reporter="puptoo",
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(input_host)

    assert existing_host.display_name == new_fqdn


def test_update_existing_host_update_display_name_from_id_using_existing_fqdn(db_create_host):
    expected_fqdn = "host1.domain1.com"
    insights_id = generate_uuid()

    existing_host = db_create_host(extra_data={"insights_id": insights_id, "display_name": None})

    db.session.commit()
    assert existing_host.display_name == str(existing_host.id)

    # Update the host
    input_host = Host(
        insights_id=insights_id,
        fqdn=expected_fqdn,
        reporter="puptoo",
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(input_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_fix_display_name_using_input_fqdn(db_create_host):
    # Create an "existing" host
    fqdn = "host1.domain1.com"
    subman_id = generate_uuid()

    existing_host = db_create_host(extra_data={"fqdn": fqdn, "subscription_manager_id": subman_id})

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    expected_fqdn = "different.domain1.com"
    input_host = Host(
        fqdn=expected_fqdn,
        subscription_manager_id=subman_id,
        display_name="",
        reporter="puptoo",
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(input_host)

    assert existing_host.display_name == expected_fqdn


def test_update_existing_host_fix_display_name_using_id(db_create_host):
    # Create an "existing" host
    insights_id = generate_uuid()

    existing_host = db_create_host(
        SYSTEM_IDENTITY,
        extra_data={
            "insights_id": insights_id,
            "display_name": None,
            "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
        },
    )

    # Clear the display_name
    existing_host.display_name = None
    db.session.commit()
    assert existing_host.display_name is None

    # Update the host
    input_host = Host(
        insights_id=insights_id,
        display_name="",
        reporter="puptoo",
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host.update(input_host)

    assert existing_host.display_name == existing_host.id


def test_host_models_missing_reporter_field():
    limited_values = {
        "account": USER_IDENTITY["account_number"],
        "fqdn": "foo.qoo.doo.noo",
        "system_profile_facts": {"number_of_cpus": 1},
    }

    # LimitedHost should be fine with the missing reporter
    LimitedHost(**limited_values)

    values = {**limited_values, "org_id": USER_IDENTITY["org_id"]}

    # Host should complain about the missing reporter field
    with pytest.raises(ValidationException):
        Host(**values)


def test_host_model_assigned_values(db_create_host, db_get_host):
    values_input = {
        "account": USER_IDENTITY["account_number"],
        "org_id": USER_IDENTITY["org_id"],
        "display_name": "display_name",
        "ansible_host": "ansible_host",
        "facts": [{"namespace": "namespace", "facts": {"key": "value"}}],
        "tags": {"namespace": {"key": ["value"]}},
        "subscription_manager_id": generate_uuid(),
        "system_profile_facts": {"number_of_cpus": 1},
        "reporter": "reporter",
        "openshift_cluster_id": uuid.uuid4(),
    }

    expected_values = {**values_input, "static_system_profile": {"number_of_cpus": 1}}
    expected_values.pop("system_profile_facts")
    inserted_host = Host(**values_input)
    db_create_host(host=inserted_host)

    def assert_values_recursively(host, expected_values):
        for key, value in expected_values.items():
            if key == "static_system_profile":
                assert_values_recursively(host.static_system_profile, value)
            elif key == "dynamic_system_profile":
                assert_values_recursively(host.dynamic_system_profile, value)
            else:
                assert getattr(host, key) == value

    selected_host = db_get_host(inserted_host.id)
    assert_values_recursively(selected_host, expected_values)


def test_host_model_invalid_openshift_cluster_id(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        subscription_manager_id=generate_uuid(),
        reporter="yupana",
        org_id=USER_IDENTITY["org_id"],
        openshift_cluster_id="invalid-uuid",
    )
    with pytest.raises(DataError):
        db_create_host(host=host)


def test_host_model_no_openshift_cluster_id_allowed(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        subscription_manager_id=generate_uuid(),
        reporter="yupana",
        org_id=USER_IDENTITY["org_id"],
        openshift_cluster_id=None,
    )
    db_create_host(host=host)


def test_host_model_default_id(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        subscription_manager_id=generate_uuid(),
        reporter="yupana",
        org_id=USER_IDENTITY["org_id"],
    )
    db_create_host(host=host)

    assert isinstance(host.id, uuid.UUID)


def test_host_model_default_timestamps(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        subscription_manager_id=generate_uuid(),
        reporter="yupana",
        org_id=USER_IDENTITY["org_id"],
    )

    before_commit = now()
    db_create_host(host=host)
    after_commit = now()

    assert isinstance(host.created_on, datetime)
    assert before_commit < host.created_on < after_commit
    assert isinstance(host.modified_on, datetime)
    assert host.modified_on < after_commit


def test_host_model_updated_timestamp(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        subscription_manager_id=generate_uuid(),
        reporter="yupana",
        org_id=USER_IDENTITY["org_id"],
    )

    before_insert_commit = now()
    db_create_host(host=host)
    after_insert_commit = now()

    host.fqdn = "ndqf"

    db.session.commit()
    after_update_commit = now()

    assert before_insert_commit < host.created_on < after_insert_commit
    assert host.modified_on < after_update_commit


def test_host_model_timestamp_timezones(db_create_host):
    host = Host(
        account=USER_IDENTITY["account_number"],
        subscription_manager_id=generate_uuid(),
        reporter="ingress",
        org_id=USER_IDENTITY["org_id"],
    )

    db_create_host(host=host)

    assert host.created_on.tzinfo
    assert host.modified_on.tzinfo


@pytest.mark.parametrize(
    "field,value",
    [("account", "00000000102"), ("display_name", "x" * 201), ("ansible_host", "x" * 256), ("reporter", "x" * 256)],
)
def test_host_model_constraints(field, value, db_create_host):
    values = {
        "account": USER_IDENTITY["account_number"],
        "subscription_manager_id": generate_uuid(),
        "org_id": USER_IDENTITY["org_id"],
        **{field: value},
    }
    # add reporter if it's missing because it is now required all the time
    if not values.get("reporter"):
        values["reporter"] = "yupana"

    host = Host(**values)

    with pytest.raises(DataError):
        db_create_host(host=host)


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
    system_profile_data = {**static_profile_data, **dynamic_profile_data, "workloads": workloads_data}
    host = db_create_host(extra_data={"system_profile_facts": system_profile_data})
    assert host.dynamic_system_profile.workloads["ansible"]["controller_version"] == "4.5.6"
    assert host.dynamic_system_profile.workloads["rhel_ai"]["variant"] == "RHEL AI"


def test_host_init_with_subscription_manager_id_sets_id(flask_app):
    """
    Host.__init__ must accept a valid ID fact supplied as an explicit field and
    correctly set the host id when USE_SUBMAN_ID is enabled.
    """
    subscription_manager_id = generate_uuid()

    # Set USE_SUBMAN_ID config
    flask_app.app.config["USE_SUBMAN_ID"] = True

    with flask_app.app.app_context():
        host = Host(
            account=USER_IDENTITY["account_number"],
            org_id=USER_IDENTITY["org_id"],
            reporter="test",
            subscription_manager_id=subscription_manager_id,
        )

        # The constructor should succeed and set id to subscription_manager_id
        assert host.id is not None
        assert str(host.id) == subscription_manager_id
        assert host.subscription_manager_id == subscription_manager_id


def test_create_host_app_data_advisor(db_create_host):
    """Test creating a HostAppDataAdvisor record."""
    host = db_create_host()
    current_time = now()

    advisor_data = HostAppDataAdvisor(
        org_id=host.org_id,
        host_id=host.id,
        last_updated=current_time,
        recommendations=5,
        incidents=2,
        critical=3,
        important=2,
        moderate=0,
        low=0,
    )

    db.session.add(advisor_data)
    db.session.commit()

    # Retrieve and verify
    retrieved = db.session.query(HostAppDataAdvisor).filter_by(org_id=host.org_id, host_id=host.id).first()

    assert retrieved is not None
    assert retrieved.org_id == host.org_id
    assert retrieved.host_id == host.id
    assert retrieved.recommendations == 5
    assert retrieved.incidents == 2
    assert retrieved.critical == 3
    assert retrieved.important == 2
    assert retrieved.moderate == 0
    assert retrieved.low == 0
    assert retrieved.last_updated == current_time


def test_create_host_app_data_vulnerability(db_create_host):
    """Test creating a HostAppDataVulnerability record."""
    host = db_create_host()
    current_time = now()

    vuln_data = HostAppDataVulnerability(
        org_id=host.org_id,
        host_id=host.id,
        last_updated=current_time,
        total_cves=150,
        critical_cves=5,
        important_cves=20,
        moderate_cves=40,
        low_cves=85,
        cves_with_security_rules=10,
        cves_with_known_exploits=3,
    )

    db.session.add(vuln_data)
    db.session.commit()

    # Retrieve and verify
    retrieved = db.session.query(HostAppDataVulnerability).filter_by(org_id=host.org_id, host_id=host.id).first()

    assert retrieved is not None
    assert retrieved.org_id == host.org_id
    assert retrieved.host_id == host.id
    assert retrieved.total_cves == 150
    assert retrieved.critical_cves == 5
    assert retrieved.important_cves == 20
    assert retrieved.moderate_cves == 40
    assert retrieved.low_cves == 85
    assert retrieved.cves_with_security_rules == 10
    assert retrieved.cves_with_known_exploits == 3
    assert retrieved.last_updated == current_time


def test_create_host_app_data_patch(db_create_host):
    """Test creating a HostAppDataPatch record."""
    host = db_create_host()
    current_time = now()
    template_uuid = uuid.uuid4()

    patch_data = HostAppDataPatch(
        org_id=host.org_id,
        host_id=host.id,
        last_updated=current_time,
        advisories_rhsa_applicable=10,
        advisories_rhba_applicable=5,
        advisories_rhea_applicable=3,
        advisories_other_applicable=2,
        advisories_rhsa_installable=8,
        advisories_rhba_installable=4,
        advisories_rhea_installable=2,
        advisories_other_installable=1,
        packages_applicable=100,
        packages_installable=50,
        packages_installed=500,
        template_name="production-template",
        template_uuid=template_uuid,
    )

    db.session.add(patch_data)
    db.session.commit()

    # Retrieve and verify
    retrieved = db.session.query(HostAppDataPatch).filter_by(org_id=host.org_id, host_id=host.id).first()

    assert retrieved is not None
    assert retrieved.org_id == host.org_id
    assert retrieved.host_id == host.id
    assert retrieved.advisories_rhsa_applicable == 10
    assert retrieved.advisories_rhba_applicable == 5
    assert retrieved.advisories_rhea_applicable == 3
    assert retrieved.advisories_other_applicable == 2
    assert retrieved.advisories_rhsa_installable == 8
    assert retrieved.advisories_rhba_installable == 4
    assert retrieved.advisories_rhea_installable == 2
    assert retrieved.advisories_other_installable == 1
    assert retrieved.packages_applicable == 100
    assert retrieved.packages_installable == 50
    assert retrieved.packages_installed == 500
    assert retrieved.template_name == "production-template"
    assert retrieved.template_uuid == template_uuid
    assert retrieved.last_updated == current_time


def test_create_host_app_data_remediations(db_create_host):
    """Test creating a HostAppDataRemediations record."""
    host = db_create_host()
    current_time = now()

    remediation_data = HostAppDataRemediations(
        org_id=host.org_id,
        host_id=host.id,
        last_updated=current_time,
        remediations_plans=3,
    )

    db.session.add(remediation_data)
    db.session.commit()

    # Retrieve and verify
    retrieved = db.session.query(HostAppDataRemediations).filter_by(org_id=host.org_id, host_id=host.id).first()

    assert retrieved is not None
    assert retrieved.org_id == host.org_id
    assert retrieved.host_id == host.id
    assert retrieved.remediations_plans == 3
    assert retrieved.last_updated == current_time


def test_create_host_app_data_compliance(db_create_host):
    """Test creating a HostAppDataCompliance record."""
    host = db_create_host()
    current_time = now()
    scan_time = now() - timedelta(days=1)
    policies = [
        {"id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "name": "Policy 1"},
        {"id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff", "name": "Policy 2"},
    ]

    compliance_data = HostAppDataCompliance(
        org_id=host.org_id,
        host_id=host.id,
        last_updated=current_time,
        policies=policies,
        last_scan=scan_time,
    )

    db.session.add(compliance_data)
    db.session.commit()

    # Retrieve and verify
    retrieved = db.session.query(HostAppDataCompliance).filter_by(org_id=host.org_id, host_id=host.id).first()

    assert retrieved is not None
    assert retrieved.org_id == host.org_id
    assert retrieved.host_id == host.id
    assert retrieved.last_scan == scan_time
    assert retrieved.last_updated == current_time
    assert retrieved.policies[0]["id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert retrieved.policies[0]["name"] == "Policy 1"
    assert retrieved.policies[1]["id"] == "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
    assert retrieved.policies[1]["name"] == "Policy 2"


def test_create_host_app_data_malware(db_create_host):
    """Test creating a HostAppDataMalware record."""
    host = db_create_host()
    current_time = now()
    scan_time = now() - timedelta(hours=2)

    malware_data = HostAppDataMalware(
        org_id=host.org_id,
        host_id=host.id,
        last_updated=current_time,
        last_status="Not affected",
        last_matches=0,
        last_scan=scan_time,
        total_matches=0,
    )

    db.session.add(malware_data)
    db.session.commit()

    # Retrieve and verify
    retrieved = db.session.query(HostAppDataMalware).filter_by(org_id=host.org_id, host_id=host.id).first()

    assert retrieved is not None
    assert retrieved.org_id == host.org_id
    assert retrieved.host_id == host.id
    assert retrieved.last_status == "Not affected"
    assert retrieved.last_matches == 0
    assert retrieved.last_scan == scan_time
    assert retrieved.last_updated == current_time
    assert retrieved.total_matches == 0


def test_update_host_app_data_advisor(db_create_host):
    """Test updating a HostAppDataAdvisor record."""
    host = db_create_host()
    current_time = now()

    advisor_data = HostAppDataAdvisor(
        org_id=host.org_id,
        host_id=host.id,
        last_updated=current_time,
        recommendations=5,
        incidents=2,
        critical=3,
        important=2,
        moderate=0,
        low=0,
    )

    db.session.add(advisor_data)
    db.session.commit()

    # Update the record
    advisor_data.recommendations = 8
    advisor_data.incidents = 3
    advisor_data.critical = 4
    advisor_data.important = 1
    advisor_data.moderate = 2
    advisor_data.low = 1
    new_time = now()
    advisor_data.last_updated = new_time
    db.session.commit()

    # Verify the updates
    retrieved = db.session.query(HostAppDataAdvisor).filter_by(org_id=host.org_id, host_id=host.id).first()

    assert retrieved.recommendations == 8
    assert retrieved.incidents == 3
    assert retrieved.critical == 4
    assert retrieved.important == 1
    assert retrieved.moderate == 2
    assert retrieved.low == 1
    assert retrieved.last_updated == new_time


def test_delete_all_app_data_types_on_host_delete(db_create_host):
    """Test that deleting a host cascades to all app data types."""
    host = db_create_host()
    current_time = now()

    # Create all types of app data
    advisor_data = HostAppDataAdvisor(
        org_id=host.org_id, host_id=host.id, last_updated=current_time, recommendations=5
    )
    vuln_data = HostAppDataVulnerability(
        org_id=host.org_id, host_id=host.id, last_updated=current_time, total_cves=150
    )
    patch_data = HostAppDataPatch(
        org_id=host.org_id, host_id=host.id, last_updated=current_time, advisories_rhsa_installable=25
    )
    remediation_data = HostAppDataRemediations(
        org_id=host.org_id, host_id=host.id, last_updated=current_time, remediations_plans=3
    )
    compliance_data = HostAppDataCompliance(
        org_id=host.org_id, host_id=host.id, last_updated=current_time, last_scan=current_time
    )
    malware_data = HostAppDataMalware(
        org_id=host.org_id, host_id=host.id, last_updated=current_time, last_status="Clean"
    )

    db.session.add_all(
        [
            advisor_data,
            vuln_data,
            patch_data,
            remediation_data,
            compliance_data,
            malware_data,
        ]
    )
    db.session.commit()

    # Delete the host
    db.session.delete(host)
    db.session.commit()

    # Verify all app data records are deleted
    assert db.session.query(HostAppDataAdvisor).filter_by(org_id=host.org_id, host_id=host.id).first() is None
    assert db.session.query(HostAppDataVulnerability).filter_by(org_id=host.org_id, host_id=host.id).first() is None
    assert db.session.query(HostAppDataPatch).filter_by(org_id=host.org_id, host_id=host.id).first() is None
    assert db.session.query(HostAppDataRemediations).filter_by(org_id=host.org_id, host_id=host.id).first() is None
    assert db.session.query(HostAppDataCompliance).filter_by(org_id=host.org_id, host_id=host.id).first() is None
    assert db.session.query(HostAppDataMalware).filter_by(org_id=host.org_id, host_id=host.id).first() is None


def test_update_display_name_skips_when_unchanged(db_create_host):
    """When display_name and reporter are the same, no assignment should happen."""
    insights_id = generate_uuid()
    input_host = Host(
        insights_id=insights_id,
        display_name="my-host",
        reporter="puptoo",
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host = db_create_host(host=input_host)

    assert existing_host.display_name == "my-host"
    assert existing_host.display_name_reporter == "puptoo"

    original_display_name = existing_host.display_name
    original_reporter = existing_host.display_name_reporter

    existing_host.update_display_name("my-host", "puptoo")

    assert existing_host.display_name == original_display_name
    assert existing_host.display_name_reporter == original_reporter


def test_update_display_name_writes_when_changed(db_create_host):
    """When display_name differs, it should be updated."""
    insights_id = generate_uuid()
    input_host = Host(
        insights_id=insights_id,
        display_name="old-name",
        reporter="puptoo",
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host = db_create_host(host=input_host)

    existing_host.update_display_name("new-name", "puptoo")

    assert existing_host.display_name == "new-name"
    assert existing_host.display_name_reporter == "puptoo"


def test_update_display_name_writes_when_reporter_changed(db_create_host):
    """When display_name is the same but reporter differs, it should update."""
    insights_id = generate_uuid()
    input_host = Host(
        insights_id=insights_id,
        display_name="my-host",
        reporter="puptoo",
        org_id=USER_IDENTITY["org_id"],
    )
    existing_host = db_create_host(host=input_host)

    existing_host.update_display_name("my-host", "yupana")

    assert existing_host.display_name == "my-host"
    assert existing_host.display_name_reporter == "yupana"
