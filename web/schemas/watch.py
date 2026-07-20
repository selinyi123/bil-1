from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WatchUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mid: int = Field(..., gt=0)

    @field_validator("mid", mode="before")
    @classmethod
    def parse_mid(cls, value: object) -> int:
        if isinstance(value, str):
            text = value.strip()
            if not text.isdigit():
                raise ValueError("MID 无效")
            return int(text)
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raise ValueError("MID 无效")
