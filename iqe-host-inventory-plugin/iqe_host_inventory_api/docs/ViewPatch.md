# ViewPatch

Data for updating an existing inventory view. All fields are optional.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**name** | **str** | The display name for the view. Must contain only letters, numbers, spaces, hyphens, underscores, periods, and apostrophes, and include at least one letter or number. | [optional]
**description** | **str** | An optional description of the view. | [optional]
**configuration** | [**ViewConfiguration**](ViewConfiguration.md) |  | [optional]
**org_wide** | **bool** | If true, the view is visible to all users in the organization. If false, only the creator can see it. | [optional]

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
