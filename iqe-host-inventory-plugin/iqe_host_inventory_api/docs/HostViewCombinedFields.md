# HostViewCombinedFields

Combined sparse fieldset supporting both system_profile and application data fields. The `system_profile` key selects system profile fields, while all other keys select application data fields. The `app_data` key is an explicit shorthand to request all app data. When omitted, all application data is returned by default but no system_profile data is included.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**system_profile** | **dict(str, bool)** | Map of field names to include. Keys are field names, values are always true. | [optional]
**app_data** | **dict(str, bool)** | Map of field names to include. Keys are field names, values are always true. | [optional]
**advisor** | **dict(str, bool)** | Map of field names to include. Keys are field names, values are always true. | [optional]
**vulnerability** | **dict(str, bool)** | Map of field names to include. Keys are field names, values are always true. | [optional]
**patch** | **dict(str, bool)** | Map of field names to include. Keys are field names, values are always true. | [optional]
**remediations** | **dict(str, bool)** | Map of field names to include. Keys are field names, values are always true. | [optional]
**compliance** | **dict(str, bool)** | Map of field names to include. Keys are field names, values are always true. | [optional]
**malware** | **dict(str, bool)** | Map of field names to include. Keys are field names, values are always true. | [optional]

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
