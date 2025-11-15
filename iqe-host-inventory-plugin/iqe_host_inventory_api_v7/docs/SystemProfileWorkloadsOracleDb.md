# SystemProfileWorkloadsOracleDb

Object containing data specific to the Oracle DB workload

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**is_running** | **bool** | Indicates if Oracle DB is running on the system | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_workloads_oracle_db import SystemProfileWorkloadsOracleDb

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileWorkloadsOracleDb from a JSON string
system_profile_workloads_oracle_db_instance = SystemProfileWorkloadsOracleDb.from_json(json)
# print the JSON string representation of the object
print(SystemProfileWorkloadsOracleDb.to_json())

# convert the object into a dict
system_profile_workloads_oracle_db_dict = system_profile_workloads_oracle_db_instance.to_dict()
# create an instance of SystemProfileWorkloadsOracleDb from a dict
system_profile_workloads_oracle_db_from_dict = SystemProfileWorkloadsOracleDb.from_dict(system_profile_workloads_oracle_db_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
