import contextlib
import os
import unittest.mock


@contextlib.contextmanager
def set_environment(new_env=None):
    new_env = new_env or {}
    patched_dict = unittest.mock.patch.dict(os.environ, new_env)
    patched_dict.start()
    os.environ.clear()
    os.environ.update(new_env)
    yield
    patched_dict.stop()


def valid_system_profile():
    return {
        "number_of_cpus": 1,
        "number_of_sockets": 2,
        "cores_per_socket": 4,
        "system_memory_bytes": 1024,
        "infrastructure_type": "massive cpu",
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
        "bios_vendor": "AMI",
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
        "cloud_provider": "Maclean's Music",
        "yum_repos": [
            {"id": "repo1", "name": "repo1", "gpgcheck": True, "enabled": True, "base_url": "http://rpms.redhat.com"}
        ],
        "dnf_modules": [{"name": "postgresql", "stream": "11"}, {"name": "java", "stream": "8"}],
        "installed_products": [
            {"name": "eap", "id": "123", "status": "UP"},
            {"name": "jbws", "id": "321", "status": "DOWN"},
        ],
        "insights_client_version": "12.0.12",
        "insights_egg_version": "120.0.1",
        "captured_date": "2020-02-13T12:08:55Z",
        "installed_packages": ["rpm1-0:0.0.1.el7.i686", "rpm1-2:0.0.1.el7.i686"],
        "installed_services": ["ndb", "krb5"],
        "enabled_services": ["ndb", "krb5"],
    }


class MockEventProducer:
    def __init__(self):
        self.event = None
        self.key = None
        self.headers = None
        self.topic = None

    def write_event(self, event, key, headers, topic):
        self.event = event
        self.key = key
        self.headers = headers
        self.topic = topic
