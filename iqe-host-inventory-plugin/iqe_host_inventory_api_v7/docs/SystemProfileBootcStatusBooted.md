# SystemProfileBootcStatusBooted


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**image** | **str** | Name of the image | [optional]
**image_digest** | **str** | Digest of the image | [optional]
**cached_image** | **str** | Name of the image | [optional]
**cached_image_digest** | **str** | Digest of the image | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_bootc_status_booted import SystemProfileBootcStatusBooted

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileBootcStatusBooted from a JSON string
system_profile_bootc_status_booted_instance = SystemProfileBootcStatusBooted.from_json(json)
# print the JSON string representation of the object
print(SystemProfileBootcStatusBooted.to_json())

# convert the object into a dict
system_profile_bootc_status_booted_dict = system_profile_bootc_status_booted_instance.to_dict()
# create an instance of SystemProfileBootcStatusBooted from a dict
system_profile_bootc_status_booted_from_dict = SystemProfileBootcStatusBooted.from_dict(system_profile_bootc_status_booted_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
