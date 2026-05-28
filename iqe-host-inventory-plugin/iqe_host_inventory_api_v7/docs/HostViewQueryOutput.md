# HostViewQueryOutput

A paginated host view that optionally includes application data joins.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | The number of items on the current page |
**page** | **int** | The page number |
**per_page** | **int** | The number of items to return per page |
**total** | **int** | Total number of items |
**results** | [**List[HostViewHost]**](HostViewHost.md) | Combined host and application entries. |

## Example

```python
from iqe_host_inventory_api_v7.models.host_view_query_output import HostViewQueryOutput

# TODO update the JSON string below
json = "{}"
# create an instance of HostViewQueryOutput from a JSON string
host_view_query_output_instance = HostViewQueryOutput.from_json(json)
# print the JSON string representation of the object
print(HostViewQueryOutput.to_json())

# convert the object into a dict
host_view_query_output_dict = host_view_query_output_instance.to_dict()
# create an instance of HostViewQueryOutput from a dict
host_view_query_output_from_dict = HostViewQueryOutput.from_dict(host_view_query_output_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
