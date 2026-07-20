from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

ALLOWED_JOB_ACTIONS = frozenset(
    {
        "login",
        "refresh_all",
        "refresh_source",
        "refresh_watch",
        "refresh_status",
        "participate",
        "participate_triple",
    }
)


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    params: dict[str, Any] | None = None


class JobStatusOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    state: str = "idle"
    action: str = ""
    label: str = ""
    source: str = "ui"
    started_at: int | None = None
    finished_at: int | None = None
    message: str = ""
    log: str = ""
    result: dict[str, Any] | None = None
    progress_step: int = 0
    progress_total: int = 0
    progress_message: str = ""


class JobStartOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool = True
    job: JobStatusOut = Field(default_factory=JobStatusOut)
