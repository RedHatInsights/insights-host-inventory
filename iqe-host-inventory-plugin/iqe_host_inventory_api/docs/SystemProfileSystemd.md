# SystemProfileSystemd

Object for whole system systemd state, as reported by systemctl status --all
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**state** | **str** | The state of the systemd subsystem |
**jobs_queued** | **int** | The number of jobs jobs_queued |
**failed** | **int** | The number of jobs failed |
**failed_services** | **list[str]** | List of all failed jobs. | [optional]

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
