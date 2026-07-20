from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UpdatesCheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    current: str = ""
    latest: str | None = None
    update_available: bool = False
    release_url: str | None = None
    download_url: str | None = None
    notes_excerpt: str | None = None
    message: str = ""
    error_kind: str | None = None
    platform: str = "unknown"
    hint: str | None = None
