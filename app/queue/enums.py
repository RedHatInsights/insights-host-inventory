from __future__ import annotations

from enum import StrEnum


class ConsumerApplication(StrEnum):
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
