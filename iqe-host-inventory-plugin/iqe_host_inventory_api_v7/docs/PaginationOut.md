# PaginationOut


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | The number of items on the current page |
**page** | **int** | The page number |
**per_page** | **int** | The number of items to return per page |
**total** | **int** | Total number of items |

## Example

```python
from iqe_host_inventory_api_v7.models.pagination_out import PaginationOut

# TODO update the JSON string below
json = "{}"
# create an instance of PaginationOut from a JSON string
pagination_out_instance = PaginationOut.from_json(json)
# print the JSON string representation of the object
print(PaginationOut.to_json())

# convert the object into a dict
pagination_out_dict = pagination_out_instance.to_dict()
# create an instance of PaginationOut from a dict
pagination_out_from_dict = PaginationOut.from_dict(pagination_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
