# PatchAppData


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**advisories_rhsa_applicable** | **int** |  | [optional]
**advisories_rhba_applicable** | **int** |  | [optional]
**advisories_rhea_applicable** | **int** |  | [optional]
**advisories_other_applicable** | **int** |  | [optional]
**advisories_rhsa_installable** | **int** |  | [optional]
**advisories_rhba_installable** | **int** |  | [optional]
**advisories_rhea_installable** | **int** |  | [optional]
**advisories_other_installable** | **int** |  | [optional]
**packages_applicable** | **int** |  | [optional]
**packages_installable** | **int** |  | [optional]
**packages_installed** | **int** |  | [optional]
**template_name** | **str** |  | [optional]
**template_uuid** | **str** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.patch_app_data import PatchAppData

# TODO update the JSON string below
json = "{}"
# create an instance of PatchAppData from a JSON string
patch_app_data_instance = PatchAppData.from_json(json)
# print the JSON string representation of the object
print(PatchAppData.to_json())

# convert the object into a dict
patch_app_data_dict = patch_app_data_instance.to_dict()
# create an instance of PatchAppData from a dict
patch_app_data_from_dict = PatchAppData.from_dict(patch_app_data_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
