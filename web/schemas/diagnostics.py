from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticsLogsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    files: list[str] = Field(default_factory=list)
    count: int = 0
    lines: list[dict[str, Any]] = Field(default_factory=list)


class DiagnosticsBundleOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    filename: str
    text: str
