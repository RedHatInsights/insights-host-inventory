import json
import subprocess
import uuid


rpm_list = subprocess.getoutput("rpm -qa").split("\n")
print("len(rpm_list):", len(rpm_list))
# print("rpm_list:", rpm_list)


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


rhsm_payload = {
    "account": "939054",
    "bios_uuid": "e56890e3-9ce5-4fb2-b677-3d84e3e4d4a9",
    "facts": [
        {
            "facts": {
                "ARCHITECTURE": "x86_64",
                "CPU_CORES": 4,
                "CPU_SOCKETS": 4,
                "IS_VIRTUAL": True,
                "MEMORY": 8,
                "RH_PROD": ["69", "408", "290"],
                "SYNC_TIMESTAMP": "2019-08-08T16:32:40.355-04:00",
                "orgId": "5389686",
            },
            "namespace": "rhsm",
        }
    ],
    "fqdn": "node01.ose.skunkfu.org",
    "ip_addresses": [
        "fe80::46:6bff:fe06:c0f0",
        "10.129.0.1",
        "172.16.10.118",
        "172.17.0.1",
        "fe80::a443:aa45:96ff:2f00",
        "127.0.0.1",
    ],
    "mac_addresses": [
        "5A:3D:18:47:EB:44",
        "02:42:B0:F1:FD:01",
        "52:54:00:CD:65:84",
        "BE:FE:93:D1:A8:20",
        "02:46:6B:06:C0:F0",
        "D6:58:86:AA:AA:40",
    ],
    "subscription_manager_id": "77ecf4c6-ab06-405c-844c-d815973de7f2",
}


qpc_payload = {
    "display_name": "dhcp-8-29-119.lab.eng.rdu2.redhat.com",
    "bios_uuid": "7E681E42-FCBE-2831-E9E2-78983C7FA869",
    "ip_addresses": ["10.8.29.119"],
    "mac_addresses": ["00:50:56:9e:bb:eb"],
    "insights_id": "137c9d58-941c-4bb9-9426-7879a367c23b",
    "subscription_manager_id": "7E681E42-FCBE-2831-E9E2-78983C7FA869",
    "rhel_machine_id": "e2c9d65ad21c4c7092ffb97a2ca744f3",
    "fqdn": "dhcp-8-29-119.lab.eng.rdu2.redhat.com",
    "facts": [
        {
            "namespace": "qpc",
            "facts": {
                "rh_product_certs": [],
                "rh_products_installed": ["RHEL", "EAP", "DCSM", "JWS", "FUSE"],
                "last_reported": "2019-08-08T15:22:38.345587",
                "source_types": ["network"],
            },
        }
    ],
    "system_profile": {
        "infrastructure_type": "virtualized",
        "arch": "x86_64",
        "os_release": "Red Hat Enterprise Linux Server release 7.5 (Maipo)",
        "os_kernel_version": "7.5 (Maipo)",
        "number_of_cpus": 2,
        "number_of_sockets": 2,
        "cores_per_socket": 1,
    },
}


system_profile = create_system_profile()


# host_id = str(uuid.uuid4())
host_id = "1d518fdd-341d-4286-803b-2507ca046a94"


account_number = "0000001"
fqdn = "fred.flintstone.com"
domainnames = ["domain1", "domain2", "domain3", "domain4", "domain5"]
hostnames1 = ["apple", "pear", "orange", "banana", "apricot", "grape"]
hostnames2 = ["coke", "pepsi", "drpepper", "mrpib", "sprite", "7up", "unsweettea", "sweettea"]


metadata_dict = {"request_id": str(uuid.uuid4()), "archive_url": "http://s3.aws.com/redhat/insights/1234567"}


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


def build_data(payload_type):
    if payload_type == "default":
        return build_host_chunk()
    elif payload_type == "rhsm":
        return rhsm_payload
    elif payload_type == "qpc":
        return qpc_payload


def build_mq_payloads(num_hosts=1, payload_type="default"):
    all_payloads = []
    for _ in range(num_hosts):
        all_payloads.append(
            str.encode(
                json.dumps(
                    {"operation": "add_host", "platform_metadata": metadata_dict, "data": build_data(payload_type)}
                )
            )
        )
    return all_payloads


def build_http_payloads(num_hosts=1, payload_type="default"):  # FIXME: Could combine with the above method?
    all_payloads = []
    for _ in range(num_hosts):
        all_payloads.append(build_data(payload_type))
    return all_payloads
