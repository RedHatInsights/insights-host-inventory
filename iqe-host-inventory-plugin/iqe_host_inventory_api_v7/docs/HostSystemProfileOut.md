# HostSystemProfileOut

Individual host record that contains only the host id and system profile

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** |  | [optional]
**system_profile** | [**SystemProfile**](SystemProfile.md) |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.host_system_profile_out import HostSystemProfileOut

# TODO update the JSON string below
json = "{}"
# create an instance of HostSystemProfileOut from a JSON string
host_system_profile_out_instance = HostSystemProfileOut.from_json(json)
# print the JSON string representation of the object
print(HostSystemProfileOut.to_json())

# convert the object into a dict
host_system_profile_out_dict = host_system_profile_out_instance.to_dict()
# create an instance of HostSystemProfileOut from a dict
host_system_profile_out_from_dict = HostSystemProfileOut.from_dict(host_system_profile_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
