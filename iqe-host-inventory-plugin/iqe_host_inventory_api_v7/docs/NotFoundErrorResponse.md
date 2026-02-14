# NotFoundErrorResponse

Error response returned when one or more requested resources are not found.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**status** | **int** | The HTTP status code. |
**title** | **str** | A short summary of the error. |
**detail** | **str** | A human-readable description of the error. |
**not_found_ids** | **List[str]** | A list of IDs that were requested but not found. This field is included when specific IDs can be identified as missing. | [optional]
**type** | **str** | The type of the error. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.not_found_error_response import NotFoundErrorResponse

# TODO update the JSON string below
json = "{}"
# create an instance of NotFoundErrorResponse from a JSON string
not_found_error_response_instance = NotFoundErrorResponse.from_json(json)
# print the JSON string representation of the object
print(NotFoundErrorResponse.to_json())

# convert the object into a dict
not_found_error_response_dict = not_found_error_response_instance.to_dict()
# create an instance of NotFoundErrorResponse from a dict
not_found_error_response_from_dict = NotFoundErrorResponse.from_dict(not_found_error_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
