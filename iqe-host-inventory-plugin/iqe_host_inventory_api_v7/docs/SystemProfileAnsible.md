# SystemProfileAnsible

Object containing data specific to Ansible Automation Platform

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**controller_version** | **str** | The ansible-tower or automation-controller version on the host | [optional]
**hub_version** | **str** | The automation-hub version on the host | [optional]
**catalog_worker_version** | **str** | The catalog-worker version on the host | [optional]
**sso_version** | **str** | The SSO version on the host | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_ansible import SystemProfileAnsible

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileAnsible from a JSON string
system_profile_ansible_instance = SystemProfileAnsible.from_json(json)
# print the JSON string representation of the object
print(SystemProfileAnsible.to_json())

# convert the object into a dict
system_profile_ansible_dict = system_profile_ansible_instance.to_dict()
# create an instance of SystemProfileAnsible from a dict
system_profile_ansible_from_dict = SystemProfileAnsible.from_dict(system_profile_ansible_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
