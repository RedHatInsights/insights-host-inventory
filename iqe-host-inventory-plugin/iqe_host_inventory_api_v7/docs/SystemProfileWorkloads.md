# SystemProfileWorkloads

Object containing information about system workloads

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**ansible** | [**SystemProfileAnsible**](SystemProfileAnsible.md) |  | [optional]
**crowdstrike** | [**SystemProfileThirdPartyServicesCrowdstrike**](SystemProfileThirdPartyServicesCrowdstrike.md) |  | [optional]
**ibm_db2** | [**SystemProfileWorkloadsIbmDb2**](SystemProfileWorkloadsIbmDb2.md) |  | [optional]
**intersystems** | [**SystemProfileIntersystems**](SystemProfileIntersystems.md) |  | [optional]
**mssql** | [**SystemProfileMssql**](SystemProfileMssql.md) |  | [optional]
**oracle_db** | [**SystemProfileWorkloadsOracleDb**](SystemProfileWorkloadsOracleDb.md) |  | [optional]
**rhel_ai** | [**SystemProfileWorkloadsRhelAi**](SystemProfileWorkloadsRhelAi.md) |  | [optional]
**sap** | [**SystemProfileSap**](SystemProfileSap.md) |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_workloads import SystemProfileWorkloads

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileWorkloads from a JSON string
system_profile_workloads_instance = SystemProfileWorkloads.from_json(json)
# print the JSON string representation of the object
print(SystemProfileWorkloads.to_json())

# convert the object into a dict
system_profile_workloads_dict = system_profile_workloads_instance.to_dict()
# create an instance of SystemProfileWorkloads from a dict
system_profile_workloads_from_dict = SystemProfileWorkloads.from_dict(system_profile_workloads_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
