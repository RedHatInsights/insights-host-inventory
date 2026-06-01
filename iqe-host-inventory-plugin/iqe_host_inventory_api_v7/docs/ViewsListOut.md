# ViewsListOut

A paginated list of inventory views.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | The number of items on the current page |
**page** | **int** | The page number |
**per_page** | **int** | The number of items to return per page |
**total** | **int** | Total number of items |
**results** | [**List[ViewOut]**](ViewOut.md) | List of inventory views. |

## Example

```python
from iqe_host_inventory_api_v7.models.views_list_out import ViewsListOut

# TODO update the JSON string below
json = "{}"
# create an instance of ViewsListOut from a JSON string
views_list_out_instance = ViewsListOut.from_json(json)
# print the JSON string representation of the object
print(ViewsListOut.to_json())

# convert the object into a dict
views_list_out_dict = views_list_out_instance.to_dict()
# create an instance of ViewsListOut from a dict
views_list_out_from_dict = ViewsListOut.from_dict(views_list_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
