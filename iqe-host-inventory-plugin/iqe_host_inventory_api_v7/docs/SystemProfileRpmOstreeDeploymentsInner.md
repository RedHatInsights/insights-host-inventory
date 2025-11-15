# SystemProfileRpmOstreeDeploymentsInner

Limited deployment information from systems managed by rpm-ostree as reported by rpm-ostree status --json

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** | ID of the deployment |
**checksum** | **str** | The checksum / commit of the deployment |
**origin** | **str** | The origin repo from which the commit was installed |
**osname** | **str** | The operating system name |
**version** | **str** | The version of the deployment | [optional]
**booted** | **bool** | Whether the deployment is currently booted |
**pinned** | **bool** | Whether the deployment is currently pinned |

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_rpm_ostree_deployments_inner import SystemProfileRpmOstreeDeploymentsInner

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileRpmOstreeDeploymentsInner from a JSON string
system_profile_rpm_ostree_deployments_inner_instance = SystemProfileRpmOstreeDeploymentsInner.from_json(json)
# print the JSON string representation of the object
print(SystemProfileRpmOstreeDeploymentsInner.to_json())

# convert the object into a dict
system_profile_rpm_ostree_deployments_inner_dict = system_profile_rpm_ostree_deployments_inner_instance.to_dict()
# create an instance of SystemProfileRpmOstreeDeploymentsInner from a dict
system_profile_rpm_ostree_deployments_inner_from_dict = SystemProfileRpmOstreeDeploymentsInner.from_dict(system_profile_rpm_ostree_deployments_inner_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
