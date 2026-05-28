# ViewConfiguration

The full visual configuration for an inventory view, including column layout, sort order, and active filters.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**columns** | [**List[ViewColumnConfig]**](ViewColumnConfig.md) | Ordered list of column configurations. |
**sort** | [**ViewSortConfig**](ViewSortConfig.md) |  | [optional]
**filters** | **Dict[str, List[str]]** | Active filter criteria. Keys are filter names, values are arrays of selected filter values. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.view_configuration import ViewConfiguration

# TODO update the JSON string below
json = "{}"
# create an instance of ViewConfiguration from a JSON string
view_configuration_instance = ViewConfiguration.from_json(json)
# print the JSON string representation of the object
print(ViewConfiguration.to_json())

# convert the object into a dict
view_configuration_dict = view_configuration_instance.to_dict()
# create an instance of ViewConfiguration from a dict
view_configuration_from_dict = ViewConfiguration.from_dict(view_configuration_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
