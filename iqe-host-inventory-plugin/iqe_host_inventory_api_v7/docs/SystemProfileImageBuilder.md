# SystemProfileImageBuilder

Object containing image builder facts

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**compliance_policy_id** | **str** | The compliance policy that was used and applied during the image build | [optional]
**compliance_profile_id** | **str** | The profile that was applied during the image build on which the compliance policy was based  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_image_builder import SystemProfileImageBuilder

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileImageBuilder from a JSON string
system_profile_image_builder_instance = SystemProfileImageBuilder.from_json(json)
# print the JSON string representation of the object
print(SystemProfileImageBuilder.to_json())

# convert the object into a dict
system_profile_image_builder_dict = system_profile_image_builder_instance.to_dict()
# create an instance of SystemProfileImageBuilder from a dict
system_profile_image_builder_from_dict = SystemProfileImageBuilder.from_dict(system_profile_image_builder_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
