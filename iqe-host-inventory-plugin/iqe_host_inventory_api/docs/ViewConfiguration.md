# ViewConfiguration

The full visual configuration for an inventory view, including column layout, sort order, and active filters.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**columns** | [**list[ViewColumnConfig]**](ViewColumnConfig.md) | Ordered list of column configurations. |
**sort** | [**ViewSortConfig**](ViewSortConfig.md) |  | [optional]
**filters** | **dict(str, list[str])** | Active filter criteria. Keys are filter names, values are arrays of selected filter values. | [optional]

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
