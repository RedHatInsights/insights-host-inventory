# SystemProfileWorkloadsAnsible

Object containing data specific to Ansible Automation Platform

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**controller_version** | **str** | The installed ansible-tower or automation-controller RPM version | [optional]
**hub_version** | **str** | The installed automation-hub RPM version | [optional]
**catalog_worker_version** | **str** | The installed catalog-worker RPM version | [optional]
**sso_version** | **str** | The installed SSO RPM version | [optional]
**receptor_version** | **str** | The installed receptor RPM version | [optional]
**runner_version** | **str** | The installed ansible-runner RPM version | [optional]
**eda_controller_version** | **str** | The installed automation-eda-controller RPM version | [optional]
**gateway_version** | **str** | The installed automation-gateway RPM version | [optional]
**containers** | [**List[Container]**](Container.md) |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_workloads_ansible import (
    SystemProfileWorkloadsAnsible,
)

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileWorkloadsAnsible from a JSON string
system_profile_workloads_ansible_instance = SystemProfileWorkloadsAnsible.from_json(json)
# print the JSON string representation of the object
print(SystemProfileWorkloadsAnsible.to_json())

# convert the object into a dict
system_profile_workloads_ansible_dict = system_profile_workloads_ansible_instance.to_dict()
# create an instance of SystemProfileWorkloadsAnsible from a dict
system_profile_workloads_ansible_from_dict = SystemProfileWorkloadsAnsible.from_dict(
    system_profile_workloads_ansible_dict
)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
