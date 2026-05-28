# ViewIn

Data required to create a new inventory view.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**name** | **str** | The display name for the view. |
**description** | **str** | An optional description of the view. | [optional]
**configuration** | [**ViewConfiguration**](ViewConfiguration.md) |  |
**org_wide** | **bool** | If true, the view is visible to all users in the organization. If false, only the creator can see it. | [optional] [default to False]

## Example

```python
from iqe_host_inventory_api_v7.models.view_in import ViewIn

# TODO update the JSON string below
json = "{}"
# create an instance of ViewIn from a JSON string
view_in_instance = ViewIn.from_json(json)
# print the JSON string representation of the object
print(ViewIn.to_json())

# convert the object into a dict
view_in_dict = view_in_instance.to_dict()
# create an instance of ViewIn from a dict
view_in_from_dict = ViewIn.from_dict(view_in_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
