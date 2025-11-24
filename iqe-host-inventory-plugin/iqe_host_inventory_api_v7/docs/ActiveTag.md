# ActiveTag

Information about a host tag

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**tag** | [**StructuredTag**](StructuredTag.md) |  |
**count** | **int** | The number of hosts with the given tag. If the value is null this indicates that the count is unknown. |

## Example

```python
from iqe_host_inventory_api_v7.models.active_tag import ActiveTag

# TODO update the JSON string below
json = "{}"
# create an instance of ActiveTag from a JSON string
active_tag_instance = ActiveTag.from_json(json)
# print the JSON string representation of the object
print(ActiveTag.to_json())

# convert the object into a dict
active_tag_dict = active_tag_instance.to_dict()
# create an instance of ActiveTag from a dict
active_tag_from_dict = ActiveTag.from_dict(active_tag_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
