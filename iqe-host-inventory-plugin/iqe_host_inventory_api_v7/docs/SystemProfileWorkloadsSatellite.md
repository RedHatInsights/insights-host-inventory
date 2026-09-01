# SystemProfileWorkloadsSatellite

Object containing data specific to the Red Hat Satellite workload

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**type** | **str** | Whether this system is a Satellite Server or Capsule | [optional]
**version** | **str** | The installed satellite or satellite-capsule RPM version | [optional]
**foremanctl_version** | **str** | The installed foremanctl RPM version | [optional]
**containers** | [**List[Container]**](Container.md) |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_workloads_satellite import SystemProfileWorkloadsSatellite

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileWorkloadsSatellite from a JSON string
system_profile_workloads_satellite_instance = SystemProfileWorkloadsSatellite.from_json(json)
# print the JSON string representation of the object
print(SystemProfileWorkloadsSatellite.to_json())

# convert the object into a dict
system_profile_workloads_satellite_dict = system_profile_workloads_satellite_instance.to_dict()
# create an instance of SystemProfileWorkloadsSatellite from a dict
system_profile_workloads_satellite_from_dict = SystemProfileWorkloadsSatellite.from_dict(system_profile_workloads_satellite_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
