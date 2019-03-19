import uuid
from marshmallow import Schema, fields, pprint, ValidationError, validates


class CanonicalFactsSchema(Schema):
    insights_id = fields.UUID()
    rhel_machine_id = fields.UUID()
    subscription_manager_id = fields.UUID()
    satellite_id = fields.UUID()
    fqdn = fields.Str()
    bios_uuid = fields.UUID()
    ip_addresses = fields.List(fields.Str())
    mac_addresses = fields.List(fields.Str())
    external_id = fields.Str()

    @validates("ip_addresses")
    def validate_ip_addresses(self, value):
        if len(value) < 1:
            raise ValidationError("Array must contain at least one item")

    @validates("mac_addresses")
    def validate_mac_addresses(self, value):
        if len(value) < 1:
            raise ValidationError("Array must contain at least one item")


class DiskDeviceSchema(Schema):
    device = fields.Str()
    label = fields.Str()
    options = fields.Dict()
    mount_point = fields.Str()
    type = fields.Str()


class YumRepoSchema(Schema):
    name = fields.Str()
    gpgcheck = fields.Bool()
    enabled = fields.Bool()
    base_url = fields.Url()


class InstalledProductSchema(Schema):
    name = fields.Str()
    id = fields.Str()
    status = fields.Str()


class NetworkInterfaceSchema(Schema):
    ipv4_addresses = fields.List(fields.Str())
    ipv6_addresses = fields.List(fields.Str())
    state = fields.Str()
    mtu = fields.Int()
    mac_address = fields.Str()
    name = fields.Str()


class SystemProfileSchema(Schema):
    number_of_cpus = fields.Int()
    number_of_sockets = fields.Int()
    cores_per_socket = fields.Int()
    system_memory_bytes = fields.Int()
    infrastructure_type = fields.Str()
    infrastructure_vendor = fields.Str()
    network_interfaces = fields.List(fields.Nested(NetworkInterfaceSchema()))
    disk_devices = fields.List(fields.Nested(DiskDeviceSchema()))
    bios_vendor = fields.Str()
    bios_version = fields.Str()
    bios_release_date = fields.Str()
    cpu_flags = fields.List(fields.Str())
    os_release = fields.Str()
    os_kernel_version = fields.Str()
    arch = fields.Str()
    kernel_modules = fields.List(fields.Str())
    last_boot_time = fields.Str()
    running_processes = fields.List(fields.Str())
    subscription_status = fields.Str()
    subscription_auto_attach = fields.Str()
    katello_agent_running = fields.Bool()
    satellite_managed = fields.Bool()
    yum_repos = fields.List(fields.Nested(YumRepoSchema()))
    installed_products = fields.List(fields.Nested(InstalledProductSchema()))
    insights_client_version = fields.Str()
    insights_egg_version = fields.Str()
    installed_packages = fields.List(fields.Str())
    installed_services = fields.List(fields.Str())
    enabled_services = fields.List(fields.Str())
