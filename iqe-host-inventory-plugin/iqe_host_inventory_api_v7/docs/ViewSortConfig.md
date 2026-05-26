# ViewSortConfig

Sort configuration for a view.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**key** | **str** | The column key to sort by. |
**direction** | **str** | The sort direction. | [optional] [default to 'desc']

## Example

```python
from iqe_host_inventory_api_v7.models.view_sort_config import ViewSortConfig

# TODO update the JSON string below
json = "{}"
# create an instance of ViewSortConfig from a JSON string
view_sort_config_instance = ViewSortConfig.from_json(json)
# print the JSON string representation of the object
print(ViewSortConfig.to_json())

# convert the object into a dict
view_sort_config_dict = view_sort_config_instance.to_dict()
# create an instance of ViewSortConfig from a dict
view_sort_config_from_dict = ViewSortConfig.from_dict(view_sort_config_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
