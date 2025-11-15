# ResourceTypesQueryOutput

A paginated list of resource-types RBAC objects.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**meta** | [**ResourceTypesPaginationOutMeta**](ResourceTypesPaginationOutMeta.md) |  |
**links** | [**ResourceTypesPaginationOutLinks**](ResourceTypesPaginationOutLinks.md) |  |
**data** | [**List[ResourceTypesOut]**](ResourceTypesOut.md) | Actual resource-types object data. |

## Example

```python
from iqe_host_inventory_api_v7.models.resource_types_query_output import ResourceTypesQueryOutput

# TODO update the JSON string below
json = "{}"
# create an instance of ResourceTypesQueryOutput from a JSON string
resource_types_query_output_instance = ResourceTypesQueryOutput.from_json(json)
# print the JSON string representation of the object
print(ResourceTypesQueryOutput.to_json())

# convert the object into a dict
resource_types_query_output_dict = resource_types_query_output_instance.to_dict()
# create an instance of ResourceTypesQueryOutput from a dict
resource_types_query_output_from_dict = ResourceTypesQueryOutput.from_dict(resource_types_query_output_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
