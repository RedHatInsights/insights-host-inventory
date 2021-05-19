import base64
import json
import os
import uuid
from datetime import datetime
from datetime import timedelta
from datetime import timezone

IDENTITY = {
    "account_number": "test",
    "type": "User",
    "auth_type": "basic-auth",
    "user": {"email": "tuser@redhat.com", "first_name": "test"},
}


apiKey = base64.b64encode(json.dumps({"identity": IDENTITY}).encode("utf-8"))


def create_system_profile():
    return {
        "owner_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        "rhc_client_id": "044e36dc-4e2b-4e69-8948-9c65a7bf4976",
        "rhc_config_state": "044e36dc-4e2b-4e69-8948-9c65a7bf4976",
        "cpu_model": "Intel(R) Xeon(R) CPU E5-2690 0 @ 2.90GHz",
        "number_of_cpus": 1,
        "number_of_sockets": 2,
        "cores_per_socket": 4,
        "system_memory_bytes": 1024,
        "infrastructure_type": "jingleheimer junction cpu",
        "infrastructure_vendor": "dell",
        "network_interfaces": [
            {
                "ipv4_addresses": ["10.10.10.1"],
                "state": "UP",
                "ipv6_addresses": ["2001:0db8:85a3:0000:0000:8a2e:0370:7334"],
                "mtu": 1500,
                "mac_address": "aa:bb:cc:dd:ee:ff",
                "type": "loopback",
                "name": "eth0",
            }
        ],
        "disk_devices": [
            {
                "device": "/dev/sdb1",
                "label": "home drive",
                "options": {"uid": "0", "ro": True},
                "mount_point": "/home",
                "type": "ext3",
            }
        ],
        "bios_vendor": "Turd Ferguson",
        "bios_version": "1.0.0uhoh",
        "bios_release_date": "10/31/2013",
        "cpu_flags": ["flag1", "flag2"],
        "os_release": "Red Hat EL 7.0.1",
        "os_kernel_version": "3.10.0",
        "arch": "x86-64",
        "last_boot_time": "12:25 Mar 19, 2019",
        "kernel_modules": ["i915", "e1000e"],
        "running_processes": ["vim", "gcc", "python"],
        "subscription_status": "valid",
        "subscription_auto_attach": "yes",
        "katello_agent_running": False,
        "satellite_managed": False,
        "is_marketplace": False,
        "yum_repos": [{"name": "repo1", "gpgcheck": True, "enabled": True, "base_url": "http://rpms.redhat.com"}],
        "installed_products": [
            {"name": "eap", "id": "123", "status": "UP"},
            {"name": "jbws", "id": "321", "status": "DOWN"},
        ],
        "insights_client_version": "12.0.12",
        "insights_egg_version": "120.0.1",
        "captured_date": "2020-02-13T12:16:00Z",
        "installed_services": ["ndb", "krb5"],
        "enabled_services": ["ndb", "krb5"],
        "selinux_current_mode": "enforcing",
        "selinux_config_file": "enforcing",
    }


def random_uuid():
    return str(uuid.uuid4())


def build_host_chunk():
    account = os.environ.get("INVENTORY_HOST_ACCOUNT", IDENTITY["account_number"])
    payload = {
        "account": account,
        # "insights_id": "2b46c31f-8fb1-5565-b7e3-119305f17489",
        "insights_id": "3c46d31f-8fc1-5565-b7e3-119305f17489",
        "subscription_manager_id": "1b36b20f-7fa0-4454-a6d2-008294e06378",
        # "provider_type": "aws",
        # "provider_id": "bb31109d-6406-458e-b492-4e3e5a30abf1", #random_uuid(),
        "display_name": "0b9e8d.foo.redhat.com",
        "tags": [
            {"namespace": "SPECIAL", "key": "key", "value": "val"},
            {"namespace": "NS3", "key": "key3", "value": "val3"},
            {"namespace": "NS1", "key": "key3", "value": "val3"},
            {"namespace": "Sat", "key": "prod", "value": None},
        ],
        "system_profile": create_system_profile(),
        "stale_timestamp": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "reporter": "me",
    }
    return payload


def build_host_payload(payload_builder=build_host_chunk):
    return payload_builder()


# for testing rhsm-conduit, comment out b64_identity and provide subscription_manager_id in host.
def build_mq_payload(payload_builder=build_host_chunk):
    message = {
        "operation": "add_host",
        "platform_metadata": {
            "request_id": random_uuid(),
            "archive_url": "http://s3.aws.com/redhat/insights/1234567",
            "b64_identity": apiKey.decode("ascii"),
        },
        "data": build_host_payload(payload_builder),
    }
    return json.dumps(message).encode("utf-8")


def build_http_payload(payload_builder=build_host_chunk):
    return build_host_payload(payload_builder)
