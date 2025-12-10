# SystemProfileSystemd

Object for whole system systemd state, as reported by systemctl status --all

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**state** | **str** | The state of the systemd subsystem |
**jobs_queued** | **int** | The number of jobs jobs_queued |
**failed** | **int** | The number of jobs failed |
**failed_services** | **List[str]** | List of all failed jobs. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_systemd import SystemProfileSystemd

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileSystemd from a JSON string
system_profile_systemd_instance = SystemProfileSystemd.from_json(json)
# print the JSON string representation of the object
print(SystemProfileSystemd.to_json())

# convert the object into a dict
system_profile_systemd_dict = system_profile_systemd_instance.to_dict()
# create an instance of SystemProfileSystemd from a dict
system_profile_systemd_from_dict = SystemProfileSystemd.from_dict(system_profile_systemd_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
