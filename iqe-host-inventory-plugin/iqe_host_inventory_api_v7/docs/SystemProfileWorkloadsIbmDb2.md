# SystemProfileWorkloadsIbmDb2

Object containing data specific to the IBM DB2 workload

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**is_running** | **bool** | Indicates if IBM DB2 is running on the system | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_workloads_ibm_db2 import SystemProfileWorkloadsIbmDb2

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileWorkloadsIbmDb2 from a JSON string
system_profile_workloads_ibm_db2_instance = SystemProfileWorkloadsIbmDb2.from_json(json)
# print the JSON string representation of the object
print(SystemProfileWorkloadsIbmDb2.to_json())

# convert the object into a dict
system_profile_workloads_ibm_db2_dict = system_profile_workloads_ibm_db2_instance.to_dict()
# create an instance of SystemProfileWorkloadsIbmDb2 from a dict
system_profile_workloads_ibm_db2_from_dict = SystemProfileWorkloadsIbmDb2.from_dict(system_profile_workloads_ibm_db2_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
