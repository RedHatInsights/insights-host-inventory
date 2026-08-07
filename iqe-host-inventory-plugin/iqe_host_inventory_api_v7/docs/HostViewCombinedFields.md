# HostViewCombinedFields

Combined sparse fieldset supporting both system_profile and application data fields. The `system_profile` key selects system profile fields, while all other keys select application data fields. The `app_data` key is an explicit shorthand to request all app data. When omitted, all application data is returned by default but no system_profile data is included.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**system_profile** | **Dict[str, bool]** | Map of field names to include. Keys are field names, values are always true. | [optional]
**app_data** | **Dict[str, bool]** | Map of field names to include. Keys are field names, values are always true. | [optional]
**advisor** | **Dict[str, bool]** | Map of field names to include. Keys are field names, values are always true. | [optional]
**vulnerability** | **Dict[str, bool]** | Map of field names to include. Keys are field names, values are always true. | [optional]
**patch** | **Dict[str, bool]** | Map of field names to include. Keys are field names, values are always true. | [optional]
**remediations** | **Dict[str, bool]** | Map of field names to include. Keys are field names, values are always true. | [optional]
**compliance** | **Dict[str, bool]** | Map of field names to include. Keys are field names, values are always true. | [optional]
**malware** | **Dict[str, bool]** | Map of field names to include. Keys are field names, values are always true. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.host_view_combined_fields import HostViewCombinedFields

# TODO update the JSON string below
json = "{}"
# create an instance of HostViewCombinedFields from a JSON string
host_view_combined_fields_instance = HostViewCombinedFields.from_json(json)
# print the JSON string representation of the object
print(HostViewCombinedFields.to_json())

# convert the object into a dict
host_view_combined_fields_dict = host_view_combined_fields_instance.to_dict()
# create an instance of HostViewCombinedFields from a dict
host_view_combined_fields_from_dict = HostViewCombinedFields.from_dict(host_view_combined_fields_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
