# SystemProfileNetworkInterface

Representation of one network interface

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**ipv4_addresses** | **List[str]** |  | [optional]
**ipv6_addresses** | **List[str]** |  | [optional]
**mtu** | **int** | MTU (Maximum transmission unit) | [optional]
**mac_address** | **str** | MAC address (with or without colons) | [optional]
**name** | **str** | Name of interface | [optional]
**state** | **str** | Interface state (UP, DOWN, UNKNOWN) | [optional]
**type** | **str** | Interface type (ether, loopback) | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_network_interface import SystemProfileNetworkInterface

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileNetworkInterface from a JSON string
system_profile_network_interface_instance = SystemProfileNetworkInterface.from_json(json)
# print the JSON string representation of the object
print(SystemProfileNetworkInterface.to_json())

# convert the object into a dict
system_profile_network_interface_dict = system_profile_network_interface_instance.to_dict()
# create an instance of SystemProfileNetworkInterface from a dict
system_profile_network_interface_from_dict = SystemProfileNetworkInterface.from_dict(system_profile_network_interface_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
