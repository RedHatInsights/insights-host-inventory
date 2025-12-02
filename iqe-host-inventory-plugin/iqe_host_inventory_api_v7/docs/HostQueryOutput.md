# HostQueryOutput

A paginated host search query result with host entries and their Inventory metadata.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | The number of items on the current page |
**page** | **int** | The page number |
**per_page** | **int** | The number of items to return per page |
**total** | **int** | Total number of items |
**results** | [**List[HostOut]**](HostOut.md) | Actual host search query result entries. |

## Example

```python
from iqe_host_inventory_api_v7.models.host_query_output import HostQueryOutput

# TODO update the JSON string below
json = "{}"
# create an instance of HostQueryOutput from a JSON string
host_query_output_instance = HostQueryOutput.from_json(json)
# print the JSON string representation of the object
print(HostQueryOutput.to_json())

# convert the object into a dict
host_query_output_dict = host_query_output_instance.to_dict()
# create an instance of HostQueryOutput from a dict
host_query_output_from_dict = HostQueryOutput.from_dict(host_query_output_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
