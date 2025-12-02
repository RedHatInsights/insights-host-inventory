# SystemProfileDiskDevice

Representation of one mounted device

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**device** | **str** |  | [optional]
**label** | **str** | User-defined mount label | [optional]
**options** | [**Dict[str, SystemProfileNestedObjectValue]**](SystemProfileNestedObjectValue.md) | An arbitrary object that does not allow empty string keys. | [optional]
**mount_point** | **str** | The mount point | [optional]
**type** | **str** | The mount type | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_disk_device import SystemProfileDiskDevice

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileDiskDevice from a JSON string
system_profile_disk_device_instance = SystemProfileDiskDevice.from_json(json)
# print the JSON string representation of the object
print(SystemProfileDiskDevice.to_json())

# convert the object into a dict
system_profile_disk_device_dict = system_profile_disk_device_instance.to_dict()
# create an instance of SystemProfileDiskDevice from a dict
system_profile_disk_device_from_dict = SystemProfileDiskDevice.from_dict(system_profile_disk_device_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
