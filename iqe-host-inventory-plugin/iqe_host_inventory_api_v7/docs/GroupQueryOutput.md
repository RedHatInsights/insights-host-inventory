# GroupQueryOutput

A paginated group search query result with group entries and their Inventory metadata.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | The number of items on the current page |
**page** | **int** | The page number |
**per_page** | **int** | The number of items to return per page |
**total** | **int** | Total number of items |
**results** | [**List[GroupOutWithHostCount]**](GroupOutWithHostCount.md) | Actual group search query result entries. |

## Example

```python
from iqe_host_inventory_api_v7.models.group_query_output import GroupQueryOutput

# TODO update the JSON string below
json = "{}"
# create an instance of GroupQueryOutput from a JSON string
group_query_output_instance = GroupQueryOutput.from_json(json)
# print the JSON string representation of the object
print(GroupQueryOutput.to_json())

# convert the object into a dict
group_query_output_dict = group_query_output_instance.to_dict()
# create an instance of GroupQueryOutput from a dict
group_query_output_from_dict = GroupQueryOutput.from_dict(group_query_output_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
