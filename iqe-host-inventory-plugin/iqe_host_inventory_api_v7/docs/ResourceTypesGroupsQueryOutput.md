# ResourceTypesGroupsQueryOutput

A paginated group search query result with group entries and their Inventory metadata in paginated resource-types response format.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**meta** | [**ResourceTypesPaginationOutMeta**](ResourceTypesPaginationOutMeta.md) |  |
**links** | [**ResourceTypesPaginationOutLinks**](ResourceTypesPaginationOutLinks.md) |  |
**data** | [**List[GroupOutWithHostCount]**](GroupOutWithHostCount.md) | Actual group search query result entries. |

## Example

```python
from iqe_host_inventory_api_v7.models.resource_types_groups_query_output import ResourceTypesGroupsQueryOutput

# TODO update the JSON string below
json = "{}"
# create an instance of ResourceTypesGroupsQueryOutput from a JSON string
resource_types_groups_query_output_instance = ResourceTypesGroupsQueryOutput.from_json(json)
# print the JSON string representation of the object
print(ResourceTypesGroupsQueryOutput.to_json())

# convert the object into a dict
resource_types_groups_query_output_dict = resource_types_groups_query_output_instance.to_dict()
# create an instance of ResourceTypesGroupsQueryOutput from a dict
resource_types_groups_query_output_from_dict = ResourceTypesGroupsQueryOutput.from_dict(resource_types_groups_query_output_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
