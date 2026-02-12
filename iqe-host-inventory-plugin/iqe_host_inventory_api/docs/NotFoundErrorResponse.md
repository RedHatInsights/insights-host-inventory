# NotFoundErrorResponse

Error response returned when one or more requested resources are not found.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**status** | **int** | The HTTP status code. |
**title** | **str** | A short summary of the error. |
**detail** | **str** | A human-readable description of the error. |
**not_found_ids** | **list[str]** | A list of IDs that were requested but not found. This field is included when specific IDs can be identified as missing. | [optional]

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
