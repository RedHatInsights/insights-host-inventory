# PatchHostIn

Data of a single host to be updated.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**ansible_host** | **str** | The ansible host name for remediations | [optional]
**display_name** | **str** | A host’s human-readable display name, e.g. in a form of a domain name. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.patch_host_in import PatchHostIn

# TODO update the JSON string below
json = "{}"
# create an instance of PatchHostIn from a JSON string
patch_host_in_instance = PatchHostIn.from_json(json)
# print the JSON string representation of the object
print(PatchHostIn.to_json())

# convert the object into a dict
patch_host_in_dict = patch_host_in_instance.to_dict()
# create an instance of PatchHostIn from a dict
patch_host_in_from_dict = PatchHostIn.from_dict(patch_host_in_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
