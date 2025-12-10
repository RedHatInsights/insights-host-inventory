# CanonicalFactsOut

## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**insights_id** | **str** | An ID defined in /etc/insights-client/machine-id. This field is considered a canonical fact. | [optional]
**subscription_manager_id** | **str** | A Red Hat Subcription Manager ID of a RHEL host.  This field is considered to be a canonical fact. | [optional]
**satellite_id** | **str** | A Red Hat Satellite ID of a RHEL host.  This field is considered to be a canonical fact. | [optional]
**bios_uuid** | **str** | A UUID of the host machine BIOS.  This field is considered to be a canonical fact. | [optional]
**ip_addresses** | **list[str]** | Host’s network IP addresses.  This field is considered to be a canonical fact. | [optional]
**fqdn** | **str** | A host’s Fully Qualified Domain Name.  This field is considered to be a canonical fact. | [optional]
**mac_addresses** | **list[str]** | Host’s network interfaces MAC addresses.  This field is considered to be a canonical fact. | [optional]
**provider_id** | **str** | Host’s reference in the external source e.g. Alibaba, AWS EC2, Azure, GCP, IBM etc. This field is one of the canonical facts and does not work without provider_type. | [optional]
**provider_type** | **str** | Type of external source e.g. Alibaba, AWS EC2, Azure, GCP, IBM, etc. This field is one of the canonical facts and does not workout provider_id. | [optional]

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
