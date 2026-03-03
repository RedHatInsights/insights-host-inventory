# SystemProfile

Representation of the system profile fields

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**owner_id** | **str** | A UUID associated with the host&#39;s RHSM certificate | [optional]
**rhc_client_id** | **str** | A UUID associated with a cloud_connector | [optional]
**rhc_config_state** | **str** | A UUID associated with the config manager state | [optional]
**cpu_model** | **str** | The cpu model name | [optional]
**number_of_cpus** | **int** |  | [optional]
**number_of_sockets** | **int** |  | [optional]
**cores_per_socket** | **int** |  | [optional]
**threads_per_core** | **int** | Number of CPU threads per CPU core. Typical values: 1, 2, 4 | [optional]
**system_memory_bytes** | **int** |  | [optional]
**infrastructure_type** | **str** |  | [optional]
**infrastructure_vendor** | **str** |  | [optional]
**network_interfaces** | [**List[SystemProfileNetworkInterface]**](SystemProfileNetworkInterface.md) |  | [optional]
**disk_devices** | [**List[SystemProfileDiskDevice]**](SystemProfileDiskDevice.md) |  | [optional]
**bios_vendor** | **str** |  | [optional]
**bios_version** | **str** |  | [optional]
**bios_release_date** | **str** |  | [optional]
**cpu_flags** | **List[str]** |  | [optional]
**systemd** | [**SystemProfileSystemd**](SystemProfileSystemd.md) |  | [optional]
**operating_system** | [**SystemProfileOperatingSystem**](SystemProfileOperatingSystem.md) |  | [optional]
**os_release** | **str** |  | [optional]
**os_kernel_version** | **str** | The kernel version represented with a three, optionally four, number scheme. | [optional]
**releasever** | **str** | Release name of the system distribution (from yum/dnf) | [optional]
**arch** | **str** |  | [optional]
**basearch** | **str** | The architecture family (from yum/dnf) | [optional]
**kernel_modules** | **List[str]** |  | [optional]
**last_boot_time** | **datetime** |  | [optional]
**running_processes** | **List[str]** |  | [optional]
**subscription_status** | **str** |  | [optional]
**subscription_auto_attach** | **str** |  | [optional]
**katello_agent_running** | **bool** |  | [optional]
**satellite_managed** | **bool** |  | [optional]
**cloud_provider** | **str** |  | [optional]
**public_ipv4_addresses** | **List[str]** |  | [optional]
**public_dns** | **List[str]** |  | [optional]
**yum_repos** | [**List[SystemProfileYumRepo]**](SystemProfileYumRepo.md) |  | [optional]
**dnf_modules** | [**List[SystemProfileDnfModule]**](SystemProfileDnfModule.md) |  | [optional]
**installed_products** | [**List[SystemProfileInstalledProduct]**](SystemProfileInstalledProduct.md) |  | [optional]
**insights_client_version** | **str** | The version number of insights client. supports wildcards | [optional]
**insights_egg_version** | **str** |  | [optional]
**captured_date** | **datetime** |  | [optional]
**installed_packages** | **List[str]** |  | [optional]
**installed_packages_delta** | **List[str]** |  | [optional]
**gpg_pubkeys** | **List[str]** |  | [optional]
**installed_services** | **List[str]** |  | [optional]
**enabled_services** | **List[str]** |  | [optional]
**sap** | [**SystemProfileSap**](SystemProfileSap.md) |  | [optional]
**sap_system** | **bool** | Indicates if SAP is installed on the system | [optional]
**sap_sids** | **List[str]** |  | [optional]
**sap_instance_number** | **str** | The instance number of the SAP HANA system (a two-digit number between 00 and 99) | [optional]
**sap_version** | **str** | The version of the SAP HANA lifecycle management program | [optional]
**tuned_profile** | **str** | Current profile resulting from command tuned-adm active | [optional]
**selinux_current_mode** | **str** | The current SELinux mode, either enforcing, permissive, or disabled | [optional]
**selinux_config_file** | **str** | The SELinux mode provided in the config file | [optional]
**is_marketplace** | **bool** | Indicates whether the host is part of a marketplace install from AWS, Azure, etc. | [optional]
**host_type** | **str** | Indicates the type of host. | [optional]
**greenboot_status** | **str** | Indicates the greenboot status of an edge device. | [optional]
**greenboot_fallback_detected** | **bool** | Indicates whether greenboot detected a rolled back update on an edge device. | [optional]
**rpm_ostree_deployments** | [**List[SystemProfileRpmOstreeDeploymentsInner]**](SystemProfileRpmOstreeDeploymentsInner.md) | The list of deployments on the system as reported by rpm-ostree status --json | [optional]
**rhsm** | [**SystemProfileRhsm**](SystemProfileRhsm.md) |  | [optional]
**system_purpose** | [**SystemProfileSystemPurpose**](SystemProfileSystemPurpose.md) |  | [optional]
**ansible** | [**SystemProfileAnsible**](SystemProfileAnsible.md) |  | [optional]
**intersystems** | [**SystemProfileIntersystems**](SystemProfileIntersystems.md) |  | [optional]
**mssql** | [**SystemProfileMssql**](SystemProfileMssql.md) |  | [optional]
**system_update_method** | **str** | System update method | [optional]
**virtual_host_uuid** | **str** | Hypervisor host identity (subscription manager id) | [optional]
**bootc_status** | [**SystemProfileBootcStatus**](SystemProfileBootcStatus.md) |  | [optional]
**conversions** | [**SystemProfileConversions**](SystemProfileConversions.md) |  | [optional]
**rhel_ai** | [**SystemProfileRhelAi**](SystemProfileRhelAi.md) |  | [optional]
**third_party_services** | [**SystemProfileThirdPartyServices**](SystemProfileThirdPartyServices.md) |  | [optional]
**image_builder** | [**SystemProfileImageBuilder**](SystemProfileImageBuilder.md) |  | [optional]
**workloads** | [**SystemProfileWorkloads**](SystemProfileWorkloads.md) |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile import SystemProfile

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfile from a JSON string
system_profile_instance = SystemProfile.from_json(json)
# print the JSON string representation of the object
print(SystemProfile.to_json())

# convert the object into a dict
system_profile_dict = system_profile_instance.to_dict()
# create an instance of SystemProfile from a dict
system_profile_from_dict = SystemProfile.from_dict(system_profile_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
