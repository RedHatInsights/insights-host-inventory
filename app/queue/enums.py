from __future__ import annotations

from enum import Enum


class ConsumerApplication(str, Enum):
    """Supported applications that send host data to Inventory.

    Inheriting from str makes these enums JSON-serializable and
    compatible with string operations.
    """

    ADVISOR = "advisor"
    VULNERABILITY = "vulnerability"
    PATCH = "patch"
    REMEDIATIONS = "remediations"
    COMPLIANCE = "compliance"
    MALWARE = "malware"
    IMAGE_BUILDER = "image_builder"

    def __str__(self):
        """Return the string value for logging/metrics."""
        return self.value

    @classmethod
    def from_string(cls, value: str) -> ConsumerApplication:
        """Convert string to enum, with validation.

        Args:
            value: String value to convert to enum

        Returns:
            ConsumerApplication enum value

        Raises:
            ValueError: If the value is not a valid application name
        """
        try:
            return cls(value)
        except ValueError:
            valid_apps = [e.value for e in cls]
            raise ValueError(f"Unknown application: {value}. Valid applications: {valid_apps}") from None
