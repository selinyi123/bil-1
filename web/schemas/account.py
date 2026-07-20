from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AckAtUnreadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current: int = Field(default=0, ge=0)
