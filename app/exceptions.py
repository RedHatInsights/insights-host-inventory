class InventoryException(Exception):
    def __init__(self, status=400, title=None, detail=None, type="about:blank", severity=None):
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type
        self.severity = severity

    def to_json(self):
        return {
            "detail": self.detail,
            "status": self.status,
            "title": self.title,
            "type": self.type,
            "severity": self.severity,
        }


class InputFormatException(InventoryException):
    def __init__(self, detail):
        InventoryException.__init__(self, title="Bad Request", detail=detail)


class ValidationException(InventoryException):
    def __init__(self, detail):
        InventoryException.__init__(self, title="Validation Error", detail=detail)
