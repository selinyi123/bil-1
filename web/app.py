from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.bilibili_login import QR_IMAGE_PATH
from src.llm_settings import (
    build_llm_config_from_inputs,
    get_llm_settings_public,
    is_llm_ready,
    load_llm_values,
    mark_llm_test_passed,
    save_llm_settings,
)
from src.user_settings import DEFAULT_PARTICIPATE_TEXT, get_participate_text, set_participate_text
from src.sources.common import is_valid_dynamic_id
from web.account_service import clear_login_cookie, get_account_profile, has_login_cookie
from web.activity_service import get_summary, invalidate_activity_cache, list_activities
from web.job_runner import runner
from src.llm_client import test_llm_connection
from src.fetch_activity_info import backfill_repost_counts
from src.status_refresh import refresh_activity_statuses
from src.app_logging import setup_logging, get_logger

setup_logging(console=False)
logger = get_logger("api")

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="bilibili_binggo 控制台", version="1.0.0")

ALLOWED_JOB_ACTIONS = frozenset({"login", "refresh_all", "refresh_status", "participate"})


class JobRequest(BaseModel):
    action: str
    params: dict[str, Any] | None = None


class ParticipateTextRequest(BaseModel):
    participate_text: str = Field(default="", max_length=233)


class LlmSettingsRequest(BaseModel):
    api_key: str = Field(default="")
    base_url: str = Field(default="")
    model_name: str = Field(default="")


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
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    return list_activities(
        status=status,
        lottery_type=type,
        draw=draw,
        q=q,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@app.post("/api/activities/refresh-status")
def api_refresh_activity_status() -> dict[str, Any]:
    account = get_account_profile()
    if not account.get("logged_in"):
        raise HTTPException(status_code=401, detail="请先扫码登录后再执行此操作")
    try:
        result = refresh_activity_statuses()
        invalidate_activity_cache()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"刷新活动状态失败：{exc}") from exc
    counts = result.get("status_counts") or {}
    listable = result.get("listable_counts") or {}
    message = (
        f"状态刷新完成：标记结束 {result.get('ended_marked', 0)} 条，"
        f"列表展示 已参加 {listable.get('已参加', 0)} / 未参加 {listable.get('未参加', 0)} / "
        f"已结束 {listable.get('已结束', 0)}"
    )
    return {"ok": True, "message": message, "result": result}


@app.post("/api/activities/backfill-heat")
def api_backfill_heat() -> dict[str, Any]:
    account = get_account_profile()
    if not account.get("logged_in"):
        raise HTTPException(status_code=401, detail="请先扫码登录后再执行此操作")
    try:
        result = backfill_repost_counts()
        invalidate_activity_cache()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"热度补全失败：{exc}") from exc
    message = f"热度补全完成：更新 {result.get('updated', 0)} 条"
    if result.get("failed"):
        message += f"，失败 {result['failed']} 条"
    return {"ok": True, "message": message, "result": result}


@app.post("/api/jobs")
def api_start_job(request: JobRequest) -> dict[str, Any]:
    if request.action not in ALLOWED_JOB_ACTIONS:
        raise HTTPException(status_code=400, detail="暂不支持该操作")
    account = get_account_profile()
    if request.action in {"participate", "refresh_all", "refresh_status"}:
        if not account.get("logged_in"):
            raise HTTPException(status_code=401, detail="请先扫码登录后再执行此操作")
    if request.action in {"participate", "refresh_all"}:
        if not is_llm_ready():
            raise HTTPException(status_code=401, detail="请先保存 LLM 配置并通过连接测试后再执行此操作")
    params = request.params or {}
    if request.action == "participate":
        dynamic_id = str(params.get("dynamic_id") or "").strip()
        if not is_valid_dynamic_id(dynamic_id):
            raise HTTPException(status_code=400, detail="活动 ID 无效")
    if not runner.start(request.action, params):
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


def _build_settings_payload() -> dict[str, Any]:
    account = get_account_profile()
    llm = get_llm_settings_public()
    logged_in = bool(account.get("logged_in"))
    return {
        "participate_text": get_participate_text(),
        "default_participate_text": DEFAULT_PARTICIPATE_TEXT,
        "llm": llm,
        "setup_complete": logged_in and bool(llm.get("ready")),
    }


@app.get("/api/settings")
def api_settings() -> dict[str, Any]:
    return _build_settings_payload()


@app.get("/api/settings/llm")
def api_get_llm_settings() -> dict[str, Any]:
    account = get_account_profile()
    llm = get_llm_settings_public()
    logged_in = bool(account.get("logged_in"))
    return {
        "llm": llm,
        "setup_complete": logged_in and bool(llm.get("ready")),
    }


@app.post("/api/settings/llm/test")
def api_test_llm_settings(request: LlmSettingsRequest) -> dict[str, Any]:
    account = get_account_profile()
    if not account.get("logged_in"):
        raise HTTPException(status_code=401, detail="请先扫码登录后再测试 LLM")
    try:
        saved = load_llm_values()
        test_key = request.api_key.strip() or saved.get("LLM_API_KEY", "").strip()
        test_base = (request.base_url or "").strip().rstrip("/")
        test_model = request.model_name.strip() or saved.get("LLM_MODEL_NAME", "").strip()
        config = build_llm_config_from_inputs(
            api_key=test_key,
            base_url=test_base,
            model_name=test_model,
        )
        endpoint = test_llm_connection(config)
        llm = mark_llm_test_passed(
            api_key=test_key,
            base_url=test_base,
            model_name=test_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logged_in = bool(account.get("logged_in"))
    return {
        "ok": True,
        "message": f"连接成功：{endpoint}",
        "llm": llm,
        "setup_complete": logged_in and bool(llm.get("ready")),
    }


@app.put("/api/settings/llm")
@app.post("/api/settings/llm")
def api_update_llm_settings(request: LlmSettingsRequest) -> dict[str, Any]:
    account = get_account_profile()
    if not account.get("logged_in"):
        raise HTTPException(status_code=401, detail="请先扫码登录后再配置 LLM")
    try:
        llm = save_llm_settings(
            api_key=request.api_key.strip() or None,
            base_url=request.base_url,
            model_name=request.model_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logged_in = bool(account.get("logged_in"))
    return {
        "llm": llm,
        "setup_complete": logged_in and bool(llm.get("ready")),
    }


@app.put("/api/settings/participate-text")
def api_update_participate_text(request: ParticipateTextRequest) -> dict[str, str]:
    if not has_login_cookie():
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
