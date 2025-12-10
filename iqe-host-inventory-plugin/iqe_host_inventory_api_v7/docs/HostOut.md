# HostOut

Data of a single host belonging to an account. Represents the hosts without its Inventory metadata.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**insights_id** | **str** | An ID defined in /etc/insights-client/machine-id. This field is considered a canonical fact. | [optional]
**subscription_manager_id** | **str** | A Red Hat Subcription Manager ID of a RHEL host.  This field is considered to be a canonical fact. | [optional]
**satellite_id** | **str** | A Red Hat Satellite ID of a RHEL host.  This field is considered to be a canonical fact. | [optional]
**bios_uuid** | **str** | A UUID of the host machine BIOS.  This field is considered to be a canonical fact. | [optional]
**ip_addresses** | **List[str]** | Host’s network IP addresses.  This field is considered to be a canonical fact. | [optional]
**fqdn** | **str** | A host’s Fully Qualified Domain Name.  This field is considered to be a canonical fact. | [optional]
**mac_addresses** | **List[str]** | Host’s network interfaces MAC addresses.  This field is considered to be a canonical fact. | [optional]
**provider_id** | **str** | Host’s reference in the external source e.g. Alibaba, AWS EC2, Azure, GCP, IBM etc. This field is one of the canonical facts and does not work without provider_type. | [optional]
**provider_type** | **str** | Type of external source e.g. Alibaba, AWS EC2, Azure, GCP, IBM, etc. This field is one of the canonical facts and does not workout provider_id. | [optional]
**display_name** | **str** | A host’s human-readable display name, e.g. in a form of a domain name. | [optional]
**ansible_host** | **str** | The ansible host name for remediations | [optional]
**account** | **str** | A Red Hat Account number that owns the host. | [optional]
**org_id** | **str** | The Org ID of the tenant that owns the host. |
**id** | **str** | A durable and reliable platform-wide host identifier. Applications should use this identifier to reference hosts. | [optional]
**created** | **datetime** | A timestamp when the entry was created. | [optional]
**updated** | **datetime** | A timestamp when the entry was last updated. | [optional]
**facts** | [**List[FactSet]**](FactSet.md) | A set of facts belonging to the host. | [optional]
**stale_timestamp** | **datetime** | Timestamp from which the host is considered stale. | [optional]
**stale_warning_timestamp** | **datetime** | Timestamp from which the host is considered too stale to be listed without an explicit toggle. | [optional]
**culled_timestamp** | **datetime** | Timestamp from which the host is considered deleted. | [optional]
**reporter** | **str** | Reporting source of the host. Used when updating the stale_timestamp. | [optional]
**per_reporter_staleness** | [**Dict[str, PerReporterStaleness]**](PerReporterStaleness.md) | Reporting source of the last checkin status, stale_timestamp, and last_check_in. | [optional]
**groups** | [**List[GroupOut]**](GroupOut.md) | The groups that the host belongs to, if any. | [optional]
**system_profile** | [**SystemProfile**](SystemProfile.md) |  | [optional]
**last_check_in** | **datetime** |  | [optional]
**openshift_cluster_id** | **str** | The OpenShift cluster ID that the host belongs to, if any. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.host_out import HostOut

# TODO update the JSON string below
json = "{}"
# create an instance of HostOut from a JSON string
host_out_instance = HostOut.from_json(json)
# print the JSON string representation of the object
print(HostOut.to_json())

# convert the object into a dict
host_out_dict = host_out_instance.to_dict()
# create an instance of HostOut from a dict
host_out_from_dict = HostOut.from_dict(host_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
