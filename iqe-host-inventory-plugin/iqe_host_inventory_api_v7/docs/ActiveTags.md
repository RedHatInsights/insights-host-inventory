# ActiveTags


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | The number of items on the current page |
**page** | **int** | The page number |
**per_page** | **int** | The number of items to return per page |
**total** | **int** | Total number of items |
**results** | [**List[ActiveTag]**](ActiveTag.md) |  |

## Example

```python
from iqe_host_inventory_api_v7.models.active_tags import ActiveTags

# TODO update the JSON string below
json = "{}"
# create an instance of ActiveTags from a JSON string
active_tags_instance = ActiveTags.from_json(json)
# print the JSON string representation of the object
print(ActiveTags.to_json())

# convert the object into a dict
active_tags_dict = active_tags_instance.to_dict()
# create an instance of ActiveTags from a dict
active_tags_from_dict = ActiveTags.from_dict(active_tags_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
