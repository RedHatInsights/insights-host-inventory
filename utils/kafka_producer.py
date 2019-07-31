import json
import logging
import os
import subprocess
import time
import uuid

from kafka import KafkaProducer

rpm_list = subprocess.getoutput("rpm -qa").split("\n")
print("len(rpm_list):", len(rpm_list))
print("rpm_list:", rpm_list)


def create_system_profile():
    return {
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
        "os_kernel_version": "Linux 2.0.1",
        "arch": "x86-64",
        "last_boot_time": "12:25 Mar 19, 2019",
        "kernel_modules": ["i915", "e1000e"],
        "running_processes": ["vim", "gcc", "python"],
        "subscription_status": "valid",
        "subscription_auto_attach": "yes",
        "katello_agent_running": False,
        "satellite_managed": False,
        "yum_repos": [{"name": "repo1", "gpgcheck": True, "enabled": True, "base_url": "http://rpms.redhat.com"}],
        "installed_products": [
            {"name": "eap", "id": "123", "status": "UP"},
            {"name": "jbws", "id": "321", "status": "DOWN"},
        ],
        "insights_client_version": "12.0.12",
        "insights_egg_version": "120.0.1",
        # "installed_packages": ["rpm1", "rpm2"],
        # "installed_packages": subprocess.getoutput("rpm -qa").split("\n"),
        # "installed_packages": rpm_list,
        "installed_services": ["ndb", "krb5"],
        "enabled_services": ["ndb", "krb5"],
    }


system_profile = create_system_profile()

host_id = str(uuid.uuid4())
host_id = "1d518fdd-341d-4286-803b-2507ca046a94"


account_number = "0000001"
fqdn = "fred.flintstone.com"


def build_host_chunk():
    payload = {
        "account": account_number,
        "insights_id": str(uuid.uuid4()),
        "bios_uuid": str(uuid.uuid4()),
        "fqdn": fqdn,
        "display_name": fqdn,
        # "ip_addresses": None,
        # "ip_addresses": ["1",],
        # "mac_addresses": None,
        "subscription_manager_id": str(uuid.uuid4()),
        "system_profile": create_system_profile(),
    }
    return payload


def build_chunk():
    payload = {
        "id": host_id,
        # "system_profile": create_system_profile(),
        "system_profile": {},
    }
    return payload


logging.basicConfig(level=logging.INFO)

TOPIC = os.environ.get("KAFKA_TOPIC")
KAFKA_GROUP = os.environ.get("KAFKA_GROUP", "inventory")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")

metadata_dict = {"request_id": str(uuid.uuid4()), "archive_url": "http://s3.aws.com/redhat/insights/1234567"}

payload = build_chunk()
payload = {"operation": "add_host", "metadata": metadata_dict, "data": build_host_chunk()}

print("type(payload)):", payload)
producer = KafkaProducer(bootstrap_servers=BOOTSTRAP_SERVERS, api_version=(0, 10))
print("TOPIC:", TOPIC)

# for _ in range(1):
payload = str.encode(json.dumps(payload))
producer.send(TOPIC, value=payload)
time.sleep(2)
