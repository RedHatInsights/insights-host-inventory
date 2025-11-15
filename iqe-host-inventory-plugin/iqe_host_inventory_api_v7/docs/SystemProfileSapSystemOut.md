# SystemProfileSapSystemOut


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**total** | **int** | Total number of items | [optional]
**count** | **int** | The number of items on the current page | [optional]
**results** | [**List[SystemProfileSapSystemOutResultsInner]**](SystemProfileSapSystemOutResultsInner.md) | The list of sap_system values on the account | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_sap_system_out import SystemProfileSapSystemOut

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileSapSystemOut from a JSON string
system_profile_sap_system_out_instance = SystemProfileSapSystemOut.from_json(json)
# print the JSON string representation of the object
print(SystemProfileSapSystemOut.to_json())

# convert the object into a dict
system_profile_sap_system_out_dict = system_profile_sap_system_out_instance.to_dict()
# create an instance of SystemProfileSapSystemOut from a dict
system_profile_sap_system_out_from_dict = SystemProfileSapSystemOut.from_dict(system_profile_sap_system_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
