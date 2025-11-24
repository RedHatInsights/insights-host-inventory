# HostOutAllOf

## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**display_name** | **str** | A host’s human-readable display name, e.g. in a form of a domain name. | [optional]
**ansible_host** | **str** | The ansible host name for remediations | [optional]
**account** | **str** | A Red Hat Account number that owns the host. | [optional]
**org_id** | **str** | The Org ID of the tenant that owns the host. |
**id** | **str** | A durable and reliable platform-wide host identifier. Applications should use this identifier to reference hosts. | [optional]
**created** | **datetime** | A timestamp when the entry was created. | [optional]
**updated** | **datetime** | A timestamp when the entry was last updated. | [optional]
**facts** | [**list[FactSet]**](FactSet.md) | A set of facts belonging to the host. | [optional]
**stale_timestamp** | **datetime** | Timestamp from which the host is considered stale. | [optional]
**stale_warning_timestamp** | **datetime** | Timestamp from which the host is considered too stale to be listed without an explicit toggle. | [optional]
**culled_timestamp** | **datetime** | Timestamp from which the host is considered deleted. | [optional]
**reporter** | **str** | Reporting source of the host. Used when updating the stale_timestamp. | [optional]
**per_reporter_staleness** | [**dict(str, PerReporterStaleness)**](PerReporterStaleness.md) | Reporting source of the last checkin status, stale_timestamp, and last_check_in. | [optional]
**groups** | [**list[GroupOut]**](GroupOut.md) | The groups that the host belongs to, if any. | [optional]
**system_profile** | [**SystemProfile**](SystemProfile.md) |  | [optional]
**last_check_in** | **datetime** |  | [optional]
**openshift_cluster_id** | **str** | The OpenShift cluster ID that the host belongs to, if any. | [optional]

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
