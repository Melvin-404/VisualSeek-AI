from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema config for all Pydantic models."""
    model_config = ConfigDict(from_attributes=True)
