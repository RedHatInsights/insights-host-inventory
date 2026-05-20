# ViewPatch

Data for updating an existing inventory view. All fields are optional.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**name** | **str** | The display name for the view. | [optional]
**description** | **str** | An optional description of the view. | [optional]
**configuration** | [**ViewConfiguration**](ViewConfiguration.md) |  | [optional]
**org_wide** | **bool** | If true, the view is visible to all users in the organization. If false, only the creator can see it. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.view_patch import ViewPatch

# TODO update the JSON string below
json = "{}"
# create an instance of ViewPatch from a JSON string
view_patch_instance = ViewPatch.from_json(json)
# print the JSON string representation of the object
print(ViewPatch.to_json())

# convert the object into a dict
view_patch_dict = view_patch_instance.to_dict()
# create an instance of ViewPatch from a dict
view_patch_from_dict = ViewPatch.from_dict(view_patch_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
