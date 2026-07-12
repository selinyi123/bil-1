from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.bilibili_login import QR_IMAGE_PATH
from src.user_settings import DEFAULT_PARTICIPATE_TEXT, get_participate_text, set_participate_text
from web.account_service import clear_login_cookie, get_account_profile
from web.activity_service import get_summary, list_activities
from web.job_runner import runner

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="bilibili_binggo 控制台", version="1.0.0")


class JobRequest(BaseModel):
    action: str
    params: dict[str, Any] | None = None


class ParticipateTextRequest(BaseModel):
    participate_text: str = Field(default="", max_length=233)


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
    if request.action in {"participate", "refresh_all"}:
        account = get_account_profile()
        if not account.get("logged_in"):
            raise HTTPException(status_code=401, detail="请先扫码登录后再执行此操作")
    if not runner.start(request.action, request.params or {}):
        raise HTTPException(status_code=409, detail="已有任务正在运行")
    return {"ok": True, "job": runner.get_status().to_dict()}


@app.post("/api/jobs/cancel")
def api_cancel_job() -> dict[str, Any]:
    if not runner.cancel():
        raise HTTPException(status_code=409, detail="当前没有可取消的任务")
    return {"ok": True, "job": runner.get_status().to_dict()}


@app.get("/api/jobs/current")
def api_current_job() -> dict[str, Any]:
    return runner.get_status().to_dict()


@app.get("/api/settings")
def api_settings() -> dict[str, str]:
    return {
        "participate_text": get_participate_text(),
        "default_participate_text": DEFAULT_PARTICIPATE_TEXT,
    }


@app.put("/api/settings/participate-text")
def api_update_participate_text(request: ParticipateTextRequest) -> dict[str, str]:
    account = get_account_profile()
    if not account.get("logged_in"):
        raise HTTPException(status_code=401, detail="请先扫码登录后再修改参与文案")
    value = set_participate_text(request.participate_text)
    return {"participate_text": value}


@app.post("/api/logout")
def api_logout() -> dict[str, Any]:
    try:
        clear_login_cookie()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"退出登录失败：{exc}") from exc
    return {"ok": True}


@app.get("/api/login/qrcode")
def api_login_qrcode() -> FileResponse:
    if not QR_IMAGE_PATH.exists():
        raise HTTPException(status_code=404, detail="二维码尚未生成")
    return FileResponse(QR_IMAGE_PATH, media_type="image/png")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
