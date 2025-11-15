# CreateCheckIn

Data required to create a check-in record for a host.

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
**checkin_frequency** | **int** | How long from now to expect another check-in (in minutes). | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.create_check_in import CreateCheckIn

# TODO update the JSON string below
json = "{}"
# create an instance of CreateCheckIn from a JSON string
create_check_in_instance = CreateCheckIn.from_json(json)
# print the JSON string representation of the object
print(CreateCheckIn.to_json())

# convert the object into a dict
create_check_in_dict = create_check_in_instance.to_dict()
# create an instance of CreateCheckIn from a dict
create_check_in_from_dict = CreateCheckIn.from_dict(create_check_in_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
