# StructuredTag


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**namespace** | **str** |  | [optional]
**key** | **str** |  | [optional]
**value** | **str** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.structured_tag import StructuredTag

# TODO update the JSON string below
json = "{}"
# create an instance of StructuredTag from a JSON string
structured_tag_instance = StructuredTag.from_json(json)
# print the JSON string representation of the object
print(StructuredTag.to_json())

# convert the object into a dict
structured_tag_dict = structured_tag_instance.to_dict()
# create an instance of StructuredTag from a dict
structured_tag_from_dict = StructuredTag.from_dict(structured_tag_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
