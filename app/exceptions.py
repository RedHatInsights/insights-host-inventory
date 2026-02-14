# mypy: disallow-untyped-defs

from __future__ import annotations

from typing import Any


class InventoryException(Exception):
    def __init__(
        self, status: int = 400, title: str | None = None, detail: str | None = None, type: str = "about:blank"
    ):
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type

    def __str__(self) -> str:
        return str(self.to_json())

    def to_json(self) -> dict[str, str | int | None]:
        return {
            "detail": self.detail,
            "status": self.status,
            "title": self.title,
            "type": self.type,
        }


class InputFormatException(InventoryException):
    def __init__(self, detail: str):
        InventoryException.__init__(self, title="Bad Request", detail=detail)


class ValidationException(InventoryException):
    def __init__(self, detail: str):
        InventoryException.__init__(self, title="Validation Error", detail=detail)


class OutboxSaveException(InventoryException):
    def __init__(self, detail: str):
        InventoryException.__init__(self, title="Outbox Save Error", detail=detail)


class ResourceNotFoundException(InventoryException):
    def __init__(self, detail: str):
        InventoryException.__init__(self, title="RBAC Resource Not Found", detail=detail)


class IdsNotFoundError(InventoryException):
    """Exception raised when requested IDs are not found."""

    def __init__(self, resource_name: str, not_found_ids: list[str] | None = None):
        self.resource_name = resource_name
        self.not_found_ids = not_found_ids
        detail = f"One or more {str.lower(resource_name)}s not found."
        InventoryException.__init__(self, status=404, title="Not Found", detail=detail)

    def to_json(self) -> dict[str, Any]:
        result: dict[str, Any] = super().to_json()
        if self.not_found_ids:
            result["not_found_ids"] = self.not_found_ids
        return result
