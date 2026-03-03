# ResourceTypesOut

Data describing a single resource-types RBAC object.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**value** | **str** | The name of the resource type | [optional]
**path** | **str** | The path for the RBAC endpoint for the resource type | [optional]
**count** | **int** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.resource_types_out import ResourceTypesOut

# TODO update the JSON string below
json = "{}"
# create an instance of ResourceTypesOut from a JSON string
resource_types_out_instance = ResourceTypesOut.from_json(json)
# print the JSON string representation of the object
print(ResourceTypesOut.to_json())

# convert the object into a dict
resource_types_out_dict = resource_types_out_instance.to_dict()
# create an instance of ResourceTypesOut from a dict
resource_types_out_from_dict = ResourceTypesOut.from_dict(resource_types_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
