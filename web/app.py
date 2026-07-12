from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.bilibili_login import QR_IMAGE_PATH
from web.account_service import get_account_profile
from web.activity_service import get_summary, list_activities
from web.job_runner import runner

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="bilibili_binggo 控制台", version="1.0.0")


class JobRequest(BaseModel):
    action: str
    params: dict[str, Any] | None = None


@app.get("/api/account")
def api_account() -> dict[str, Any]:
    return get_account_profile()


@app.get("/api/summary")
def api_summary() -> dict[str, Any]:
    payload = get_summary()
    payload["job"] = runner.get_status().to_dict()
    return payload


@app.get("/api/activities")
def api_activities(
    status: str | None = Query(default=None),
    type: str | None = Query(default=None, alias="type"),
    draw: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    return list_activities(
        status=status,
        lottery_type=type,
        draw=draw,
        q=q,
        page=page,
        page_size=page_size,
    )


@app.post("/api/jobs")
def api_start_job(request: JobRequest) -> dict[str, Any]:
    if not runner.start(request.action, request.params or {}):
        raise HTTPException(status_code=409, detail="已有任务正在运行")
    return {"ok": True, "job": runner.get_status().to_dict()}


@app.get("/api/jobs/current")
def api_current_job() -> dict[str, Any]:
    return runner.get_status().to_dict()


@app.get("/api/login/qrcode")
def api_login_qrcode() -> FileResponse:
    if not QR_IMAGE_PATH.exists():
        raise HTTPException(status_code=404, detail="二维码尚未生成")
    return FileResponse(QR_IMAGE_PATH, media_type="image/png")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
