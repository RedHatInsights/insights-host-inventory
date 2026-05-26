# RemediationsAppData


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**remediations_plans** | **int** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.remediations_app_data import RemediationsAppData

# TODO update the JSON string below
json = "{}"
# create an instance of RemediationsAppData from a JSON string
remediations_app_data_instance = RemediationsAppData.from_json(json)
# print the JSON string representation of the object
print(RemediationsAppData.to_json())

# convert the object into a dict
remediations_app_data_dict = remediations_app_data_instance.to_dict()
# create an instance of RemediationsAppData from a dict
remediations_app_data_from_dict = RemediationsAppData.from_dict(remediations_app_data_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
