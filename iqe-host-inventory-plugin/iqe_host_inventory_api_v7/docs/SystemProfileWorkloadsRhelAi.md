# SystemProfileWorkloadsRhelAi

Object containing information about RHEL AI

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**variant** | **str** | RHEL AI VARIANT | [optional]
**rhel_ai_version_id** | **str** | RHEL AI VERSION ID | [optional]
**gpu_models** | [**List[SystemProfileWorkloadsRhelAiGpuModelsInner]**](SystemProfileWorkloadsRhelAiGpuModelsInner.md) | The list of GPU models on the host | [optional]
**ai_models** | **List[str]** | The list of AI models available on the host | [optional]
**free_disk_storage** | **str** | The free storage available on the host | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_workloads_rhel_ai import SystemProfileWorkloadsRhelAi

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileWorkloadsRhelAi from a JSON string
system_profile_workloads_rhel_ai_instance = SystemProfileWorkloadsRhelAi.from_json(json)
# print the JSON string representation of the object
print(SystemProfileWorkloadsRhelAi.to_json())

# convert the object into a dict
system_profile_workloads_rhel_ai_dict = system_profile_workloads_rhel_ai_instance.to_dict()
# create an instance of SystemProfileWorkloadsRhelAi from a dict
system_profile_workloads_rhel_ai_from_dict = SystemProfileWorkloadsRhelAi.from_dict(system_profile_workloads_rhel_ai_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
