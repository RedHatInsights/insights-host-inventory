# ResourceTypesPaginationOutLinks

A collection of pagination links for resource-types endpoints

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**first** | **str** | The URI path for the first page in the pagination |
**previous** | **str** | The URI path for the previous page in the pagination |
**next** | **str** | The URI path for the next page in the pagination |
**last** | **str** | The URI path for the last page in the pagination |

## Example

```python
from iqe_host_inventory_api_v7.models.resource_types_pagination_out_links import ResourceTypesPaginationOutLinks

# TODO update the JSON string below
json = "{}"
# create an instance of ResourceTypesPaginationOutLinks from a JSON string
resource_types_pagination_out_links_instance = ResourceTypesPaginationOutLinks.from_json(json)
# print the JSON string representation of the object
print(ResourceTypesPaginationOutLinks.to_json())

# convert the object into a dict
resource_types_pagination_out_links_dict = resource_types_pagination_out_links_instance.to_dict()
# create an instance of ResourceTypesPaginationOutLinks from a dict
resource_types_pagination_out_links_from_dict = ResourceTypesPaginationOutLinks.from_dict(resource_types_pagination_out_links_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
