# FactSet

A set of string facts belonging to a single namespace.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**namespace** | **str** | A namespace the facts belong to. |
**facts** | **object** | The facts themselves. |

## Example

```python
from iqe_host_inventory_api_v7.models.fact_set import FactSet

# TODO update the JSON string below
json = "{}"
# create an instance of FactSet from a JSON string
fact_set_instance = FactSet.from_json(json)
# print the JSON string representation of the object
print(FactSet.to_json())

# convert the object into a dict
fact_set_dict = fact_set_instance.to_dict()
# create an instance of FactSet from a dict
fact_set_from_dict = FactSet.from_dict(fact_set_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
