"""API response object."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Generic
from typing import TypeVar

from pydantic import BaseModel
from pydantic import Field
from pydantic import StrictBytes
from pydantic import StrictInt

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """
    API response object
    """

    status_code: StrictInt = Field(description="HTTP status code")
    headers: Mapping[str, str] | None = Field(None, description="HTTP headers")
    data: T = Field(description="Deserialized data given the data type")
    raw_data: StrictBytes = Field(description="Raw data (HTTP response body)")

    model_config = {"arbitrary_types_allowed": True}
