# SystemProfileYumRepo

Representation of one yum repository

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** |  | [optional]
**name** | **str** |  | [optional]
**gpgcheck** | **bool** |  | [optional]
**enabled** | **bool** |  | [optional]
**base_url** | **str** |  | [optional]
**mirrorlist** | **str** | URL of a mirrorlist for the repository | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_yum_repo import SystemProfileYumRepo

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileYumRepo from a JSON string
system_profile_yum_repo_instance = SystemProfileYumRepo.from_json(json)
# print the JSON string representation of the object
print(SystemProfileYumRepo.to_json())

# convert the object into a dict
system_profile_yum_repo_dict = system_profile_yum_repo_instance.to_dict()
# create an instance of SystemProfileYumRepo from a dict
system_profile_yum_repo_from_dict = SystemProfileYumRepo.from_dict(system_profile_yum_repo_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
