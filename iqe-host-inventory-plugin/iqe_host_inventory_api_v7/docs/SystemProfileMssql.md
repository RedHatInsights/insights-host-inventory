# SystemProfileMssql

Object containing data specific to the MS SQL workload

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**version** | **str** | MSSQL version number | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_mssql import SystemProfileMssql

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileMssql from a JSON string
system_profile_mssql_instance = SystemProfileMssql.from_json(json)
# print the JSON string representation of the object
print(SystemProfileMssql.to_json())

# convert the object into a dict
system_profile_mssql_dict = system_profile_mssql_instance.to_dict()
# create an instance of SystemProfileMssql from a dict
system_profile_mssql_from_dict = SystemProfileMssql.from_dict(system_profile_mssql_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
