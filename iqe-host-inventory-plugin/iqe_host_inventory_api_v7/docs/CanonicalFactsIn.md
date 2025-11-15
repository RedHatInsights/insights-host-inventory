# CanonicalFactsIn


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**insights_id** | [**CanonicalFactsInAllOfInsightsId**](CanonicalFactsInAllOfInsightsId.md) |  | [optional]
**subscription_manager_id** | [**CanonicalFactsInAllOfSubscriptionManagerId**](CanonicalFactsInAllOfSubscriptionManagerId.md) |  | [optional]
**satellite_id** | [**CanonicalFactsInAllOfSatelliteId**](CanonicalFactsInAllOfSatelliteId.md) |  | [optional]
**bios_uuid** | [**CanonicalFactsInAllOfBiosUuid**](CanonicalFactsInAllOfBiosUuid.md) |  | [optional]
**ip_addresses** | **List[str]** |  | [optional]
**fqdn** | **str** |  | [optional]
**mac_addresses** | **List[str]** |  | [optional]
**provider_id** | **str** |  | [optional]
**provider_type** | **str** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.canonical_facts_in import CanonicalFactsIn

# TODO update the JSON string below
json = "{}"
# create an instance of CanonicalFactsIn from a JSON string
canonical_facts_in_instance = CanonicalFactsIn.from_json(json)
# print the JSON string representation of the object
print(CanonicalFactsIn.to_json())

# convert the object into a dict
canonical_facts_in_dict = canonical_facts_in_instance.to_dict()
# create an instance of CanonicalFactsIn from a dict
canonical_facts_in_from_dict = CanonicalFactsIn.from_dict(canonical_facts_in_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
