# SystemProfileByHostOut

Structure of the output of the host system profile query

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | The number of items on the current page |
**page** | **int** | The page number |
**per_page** | **int** | The number of items to return per page |
**total** | **int** | Total number of items |
**results** | [**List[HostSystemProfileOut]**](HostSystemProfileOut.md) | Actual host search query result entries. |

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_by_host_out import SystemProfileByHostOut

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileByHostOut from a JSON string
system_profile_by_host_out_instance = SystemProfileByHostOut.from_json(json)
# print the JSON string representation of the object
print(SystemProfileByHostOut.to_json())

# convert the object into a dict
system_profile_by_host_out_dict = system_profile_by_host_out_instance.to_dict()
# create an instance of SystemProfileByHostOut from a dict
system_profile_by_host_out_from_dict = SystemProfileByHostOut.from_dict(system_profile_by_host_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
