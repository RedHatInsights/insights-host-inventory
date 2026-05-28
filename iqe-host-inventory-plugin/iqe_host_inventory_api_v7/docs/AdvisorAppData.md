# AdvisorAppData


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**recommendations** | **int** |  | [optional]
**incidents** | **int** |  | [optional]
**critical** | **int** |  | [optional]
**important** | **int** |  | [optional]
**moderate** | **int** |  | [optional]
**low** | **int** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.advisor_app_data import AdvisorAppData

# TODO update the JSON string below
json = "{}"
# create an instance of AdvisorAppData from a JSON string
advisor_app_data_instance = AdvisorAppData.from_json(json)
# print the JSON string representation of the object
print(AdvisorAppData.to_json())

# convert the object into a dict
advisor_app_data_dict = advisor_app_data_instance.to_dict()
# create an instance of AdvisorAppData from a dict
advisor_app_data_from_dict = AdvisorAppData.from_dict(advisor_app_data_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
