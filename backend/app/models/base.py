"""Base class for every shared contract."""

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """Rejects unknown fields and turns each field's docstring into its schema description."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)
