# SystemProfileRhelAi

Object containing information about RHEL AI

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**variant** | **str** | RHEL AI VARIANT | [optional]
**rhel_ai_version_id** | **str** | RHEL AI VERSION ID | [optional]
**amd_gpu_models** | **List[str]** | Model name of AMD GPUs | [optional]
**intel_gaudi_hpu_models** | **List[str]** | Model name of Intel Gaudi HPUs | [optional]
**nvidia_gpu_models** | **List[str]** | Model name of Nvidia GPUs in the GPU index order | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_rhel_ai import SystemProfileRhelAi

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileRhelAi from a JSON string
system_profile_rhel_ai_instance = SystemProfileRhelAi.from_json(json)
# print the JSON string representation of the object
print(SystemProfileRhelAi.to_json())

# convert the object into a dict
system_profile_rhel_ai_dict = system_profile_rhel_ai_instance.to_dict()
# create an instance of SystemProfileRhelAi from a dict
system_profile_rhel_ai_from_dict = SystemProfileRhelAi.from_dict(system_profile_rhel_ai_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
