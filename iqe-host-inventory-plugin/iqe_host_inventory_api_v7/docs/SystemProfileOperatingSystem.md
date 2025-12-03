# SystemProfileOperatingSystem

Object for OS details. Supports range operations

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**major** | **int** | Major release of OS (aka the x version) |
**minor** | **int** | Minor release of OS (aka the y version) |
**name** | **str** | Name of the distro/os |

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_operating_system import SystemProfileOperatingSystem

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileOperatingSystem from a JSON string
system_profile_operating_system_instance = SystemProfileOperatingSystem.from_json(json)
# print the JSON string representation of the object
print(SystemProfileOperatingSystem.to_json())

# convert the object into a dict
system_profile_operating_system_dict = system_profile_operating_system_instance.to_dict()
# create an instance of SystemProfileOperatingSystem from a dict
system_profile_operating_system_from_dict = SystemProfileOperatingSystem.from_dict(system_profile_operating_system_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
