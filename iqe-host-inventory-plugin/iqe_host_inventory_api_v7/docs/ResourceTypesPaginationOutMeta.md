# ResourceTypesPaginationOutMeta

The metadata for resource-types responses

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | The total number of objects returned by the query. |

## Example

```python
from iqe_host_inventory_api_v7.models.resource_types_pagination_out_meta import ResourceTypesPaginationOutMeta

# TODO update the JSON string below
json = "{}"
# create an instance of ResourceTypesPaginationOutMeta from a JSON string
resource_types_pagination_out_meta_instance = ResourceTypesPaginationOutMeta.from_json(json)
# print the JSON string representation of the object
print(ResourceTypesPaginationOutMeta.to_json())

# convert the object into a dict
resource_types_pagination_out_meta_dict = resource_types_pagination_out_meta_instance.to_dict()
# create an instance of ResourceTypesPaginationOutMeta from a dict
resource_types_pagination_out_meta_from_dict = ResourceTypesPaginationOutMeta.from_dict(resource_types_pagination_out_meta_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
