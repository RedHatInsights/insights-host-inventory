# SystemProfileSap

Object containing data specific to the SAP workload

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**sap_system** | **bool** | Indicates if SAP is installed on the system | [optional]
**sids** | **List[str]** |  | [optional]
**instance_number** | **str** | The instance number of the SAP HANA system (a two-digit number between 00 and 99) | [optional]
**version** | **str** | The version of the SAP HANA lifecycle management program | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_sap import SystemProfileSap

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileSap from a JSON string
system_profile_sap_instance = SystemProfileSap.from_json(json)
# print the JSON string representation of the object
print(SystemProfileSap.to_json())

# convert the object into a dict
system_profile_sap_dict = system_profile_sap_instance.to_dict()
# create an instance of SystemProfileSap from a dict
system_profile_sap_from_dict = SystemProfileSap.from_dict(system_profile_sap_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
