# SystemProfileBootcStatus

Object containing image data from command bootc status

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**booted** | [**SystemProfileBootcStatusBooted**](SystemProfileBootcStatusBooted.md) |  | [optional]
**rollback** | [**SystemProfileBootcStatusBooted**](SystemProfileBootcStatusBooted.md) |  | [optional]
**staged** | [**SystemProfileBootcStatusBooted**](SystemProfileBootcStatusBooted.md) |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_bootc_status import SystemProfileBootcStatus

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileBootcStatus from a JSON string
system_profile_bootc_status_instance = SystemProfileBootcStatus.from_json(json)
# print the JSON string representation of the object
print(SystemProfileBootcStatus.to_json())

# convert the object into a dict
system_profile_bootc_status_dict = system_profile_bootc_status_instance.to_dict()
# create an instance of SystemProfileBootcStatus from a dict
system_profile_bootc_status_from_dict = SystemProfileBootcStatus.from_dict(system_profile_bootc_status_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
