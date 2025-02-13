# mypy: disallow-untyped-defs

from __future__ import annotations


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
