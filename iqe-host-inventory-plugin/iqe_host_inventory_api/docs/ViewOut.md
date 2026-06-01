# ViewOut

Full representation of an inventory view returned by the API.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** | The unique identifier of the view. |
**org_id** | **str** | The organization ID that owns the view. Null for system views. | [optional]
**name** | **str** | The display name for the view. |
**description** | **str** | An optional description of the view. | [optional]
**configuration** | [**ViewConfiguration**](ViewConfiguration.md) |  |
**org_wide** | **bool** | Whether the view is visible to the entire organization. |
**is_system_view** | **bool** | True if this is a read-only system view (Red Hat preset). System views cannot be updated or deleted, but can be cloned. |
**is_owner** | **bool** | True if the requesting user is the creator of this view. Only the owner can update or delete a view. |
**created_by** | **str** | The username of the view creator. | [optional]
**created_at** | **datetime** | Timestamp when the view was created. |
**updated_at** | **datetime** | Timestamp when the view was last updated. |

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
