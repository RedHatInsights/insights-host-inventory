# SystemProfileRpmOstreeDeployments

Limited deployment information from systems managed by rpm-ostree as reported by rpm-ostree status --json
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** | ID of the deployment |
**checksum** | **str** | The checksum / commit of the deployment |
**origin** | **str** | The origin repo from which the commit was installed |
**osname** | **str** | The operating system name |
**version** | **str** | The version of the deployment | [optional]
**booted** | **bool** | Whether the deployment is currently booted |
**pinned** | **bool** | Whether the deployment is currently pinned |

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
