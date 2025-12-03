# ResourceTypesPaginationOut


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**meta** | [**ResourceTypesPaginationOutMeta**](ResourceTypesPaginationOutMeta.md) |  |
**links** | [**ResourceTypesPaginationOutLinks**](ResourceTypesPaginationOutLinks.md) |  |

## Example

```python
from iqe_host_inventory_api_v7.models.resource_types_pagination_out import ResourceTypesPaginationOut

# TODO update the JSON string below
json = "{}"
# create an instance of ResourceTypesPaginationOut from a JSON string
resource_types_pagination_out_instance = ResourceTypesPaginationOut.from_json(json)
# print the JSON string representation of the object
print(ResourceTypesPaginationOut.to_json())

# convert the object into a dict
resource_types_pagination_out_dict = resource_types_pagination_out_instance.to_dict()
# create an instance of ResourceTypesPaginationOut from a dict
resource_types_pagination_out_from_dict = ResourceTypesPaginationOut.from_dict(resource_types_pagination_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
