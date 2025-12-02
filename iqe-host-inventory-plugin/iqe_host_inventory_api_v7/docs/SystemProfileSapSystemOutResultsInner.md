# SystemProfileSapSystemOutResultsInner


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**value** | [**SystemProfileSapSystemOutResultsInnerValue**](SystemProfileSapSystemOutResultsInnerValue.md) |  | [optional]
**count** | **int** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_sap_system_out_results_inner import SystemProfileSapSystemOutResultsInner

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileSapSystemOutResultsInner from a JSON string
system_profile_sap_system_out_results_inner_instance = SystemProfileSapSystemOutResultsInner.from_json(json)
# print the JSON string representation of the object
print(SystemProfileSapSystemOutResultsInner.to_json())

# convert the object into a dict
system_profile_sap_system_out_results_inner_dict = system_profile_sap_system_out_results_inner_instance.to_dict()
# create an instance of SystemProfileSapSystemOutResultsInner from a dict
system_profile_sap_system_out_results_inner_from_dict = SystemProfileSapSystemOutResultsInner.from_dict(system_profile_sap_system_out_results_inner_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
