# ViewColumnConfig

Configuration for a single column in a view.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**key** | **str** | The column key identifier, e.g. \&quot;insights_id\&quot;, \&quot;compliance.last_scan\&quot;, \&quot;advisor.recommendations\&quot;. |
**visible** | **bool** | Whether the column is visible in the view. | [optional] [default to True]

## Example

```python
from iqe_host_inventory_api_v7.models.view_column_config import ViewColumnConfig

# TODO update the JSON string below
json = "{}"
# create an instance of ViewColumnConfig from a JSON string
view_column_config_instance = ViewColumnConfig.from_json(json)
# print the JSON string representation of the object
print(ViewColumnConfig.to_json())

# convert the object into a dict
view_column_config_dict = view_column_config_instance.to_dict()
# create an instance of ViewColumnConfig from a dict
view_column_config_from_dict = ViewColumnConfig.from_dict(view_column_config_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
