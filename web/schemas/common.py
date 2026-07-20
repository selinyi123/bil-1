from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    detail: Any = None


class ErrorBody(BaseModel):
    """失败响应形状（含兼容字段 detail）。"""

    model_config = ConfigDict(extra="forbid")

    error: ErrorObject
    detail: str


class OkResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool = True
