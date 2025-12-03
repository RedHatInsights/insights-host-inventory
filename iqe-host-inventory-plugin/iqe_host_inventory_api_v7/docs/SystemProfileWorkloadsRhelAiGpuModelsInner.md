# SystemProfileWorkloadsRhelAiGpuModelsInner

Object containing data specific to a GPU model

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**name** | **str** | The name of GPU model | [optional]
**vendor** | **str** | The vendor of GPU model | [optional]
**memory** | **str** | The memory of GPU model | [optional]
**count** | **int** | The count of this specific GPU model | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_workloads_rhel_ai_gpu_models_inner import SystemProfileWorkloadsRhelAiGpuModelsInner

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileWorkloadsRhelAiGpuModelsInner from a JSON string
system_profile_workloads_rhel_ai_gpu_models_inner_instance = SystemProfileWorkloadsRhelAiGpuModelsInner.from_json(json)
# print the JSON string representation of the object
print(SystemProfileWorkloadsRhelAiGpuModelsInner.to_json())

# convert the object into a dict
system_profile_workloads_rhel_ai_gpu_models_inner_dict = system_profile_workloads_rhel_ai_gpu_models_inner_instance.to_dict()
# create an instance of SystemProfileWorkloadsRhelAiGpuModelsInner from a dict
system_profile_workloads_rhel_ai_gpu_models_inner_from_dict = SystemProfileWorkloadsRhelAiGpuModelsInner.from_dict(system_profile_workloads_rhel_ai_gpu_models_inner_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
