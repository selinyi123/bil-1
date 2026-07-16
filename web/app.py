from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from src.bilibili_login import QR_IMAGE_PATH
from src.llm_settings import (
    build_llm_config_from_inputs,
    get_llm_settings_public,
    is_llm_ready,
    load_llm_values,
    mark_llm_test_passed,
    save_llm_settings,
)
from src.user_settings import (
    DEFAULT_PARTICIPATE_FALLBACK_TEXT,
    DEFAULT_PARTICIPATE_TEXT,
    DEFAULT_PARTICIPATE_TEXT_MODE,
    get_participate_fallback_text,
    get_participate_text,
    get_participate_text_mode,
    set_participate_fallback_text,
    set_participate_text,
    set_participate_text_mode,
)
from src.watch_sync import MAX_WINDOW_SECONDS, OUTPUT_PATH as WATCH_OUTPUT_PATH, compute_sync_window
from src.watch_users import add_watch_user, get_watch_users_payload, remove_watch_user, seed_from_candidates_if_empty
from web.account_service import ack_at_unread_notice, clear_login_cookie, get_account_extras, get_account_profile
from web.activity_service import (
    ACTIVITY_PAGE_SIZE,
    get_summary,
    invalidate_activity_cache,
    list_activities,
    summarize_triple_participate_targets,
)
from web.job_runner import runner
from src.llm_client import test_llm_connection
from src.sources.common import is_valid_dynamic_id, load_previous_output
from src.state_store import get_watch_last_synced_at
from src.app_logging import setup_logging, get_logger
from src.app_paths import ensure_user_dirs

ensure_user_dirs()
setup_logging(console=False)
logger = get_logger("api")

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="bilibili_binggo 控制台", version="3.0.5")

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
    action: str
    params: dict[str, Any] | None = None


class ParticipateTextRequest(BaseModel):
    participate_text: str | None = Field(default=None, max_length=233)
    participate_fallback_text: str | None = Field(default=None, max_length=233)
    participate_text_mode: str | None = None


class LlmSettingsRequest(BaseModel):
    api_key: str = Field(default="")
    base_url: str = Field(default="")
    model_name: str = Field(default="")


class AckAtUnreadRequest(BaseModel):
    current: int = Field(default=0, ge=0)


class WatchUserRequest(BaseModel):
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


@app.get("/api/watch-users")
def api_watch_users() -> dict[str, Any]:
    seed_from_candidates_if_empty()
    payload = get_watch_users_payload(ensure_seeded=False)
    now = int(time.time())
    last_synced_at = get_watch_last_synced_at()
    window_start, window_end = compute_sync_window(now=now, last_synced_at=last_synced_at)
    payload["last_synced_at"] = last_synced_at
    payload["max_window_seconds"] = MAX_WINDOW_SECONDS
    payload["next_window"] = {"start": window_start, "end": window_end}
    watch_data = load_previous_output(WATCH_OUTPUT_PATH) or {}
    payload["last_scan_link_count"] = int(watch_data.get("link_count") or 0)
    return payload


@app.post("/api/watch-users")
def api_add_watch_user(request: WatchUserRequest) -> dict[str, Any]:
    account = get_account_profile()
    if not account.get("logged_in"):
        raise HTTPException(status_code=401, detail="请先扫码登录后再管理监控用户")
    try:
        user = add_watch_user(mid=request.mid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"保存监控用户失败：{exc}") from exc
    name_fallback = str(request.mid) == user.name
    return {"ok": True, "user": user.to_dict(), "name_fallback": name_fallback}


@app.delete("/api/watch-users/{mid}")
def api_remove_watch_user(mid: int) -> dict[str, Any]:
    account = get_account_profile()
    if not account.get("logged_in"):
        raise HTTPException(status_code=401, detail="请先扫码登录后再管理监控用户")
    if mid <= 0:
        raise HTTPException(status_code=400, detail="MID 无效")
    try:
        removed = remove_watch_user(mid=mid)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"删除监控用户失败：{exc}") from exc
    if not removed:
        raise HTTPException(status_code=404, detail="用户不在监控列表中")
    return {"ok": True}


@app.get("/api/account")
def api_account() -> dict[str, Any]:
    return get_account_profile()


@app.get("/api/account/extras")
def api_account_extras() -> dict[str, Any]:
    try:
        return get_account_extras()
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/api/account/ack-at-unread")
def api_ack_at_unread(request: AckAtUnreadRequest) -> dict[str, Any]:
    try:
        return ack_at_unread_notice(request.current)
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"保存提醒状态失败：{exc}") from exc


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
    draw_window: str | None = Query(default=None),
    q: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=ACTIVITY_PAGE_SIZE, ge=1, le=ACTIVITY_PAGE_SIZE),
) -> dict[str, Any]:
    return list_activities(
        status=status,
        lottery_type=type,
        draw=draw,
        draw_window=draw_window,
        q=q,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@app.get("/api/activities/triple-targets")
def api_triple_participate_targets(
    status: str | None = Query(default=None),
    type: str | None = Query(default=None, alias="type"),
    draw: str | None = Query(default=None),
    draw_window: str | None = Query(default=None),
    q: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
) -> dict[str, Any]:
    return summarize_triple_participate_targets(
        status=status,
        lottery_type=type,
        draw=draw,
        draw_window=draw_window,
        q=q,
        sort=sort,
        order=order,
    )


@app.post("/api/jobs")
def api_start_job(request: JobRequest) -> dict[str, Any]:
    if request.action not in ALLOWED_JOB_ACTIONS:
        raise HTTPException(status_code=400, detail="暂不支持该操作")
    account = get_account_profile()
    if request.action in {
        "participate",
        "participate_triple",
        "refresh_all",
        "refresh_source",
        "refresh_status",
        "refresh_watch",
    }:
        if not account.get("logged_in"):
            raise HTTPException(status_code=401, detail="请先扫码登录后再执行此操作")
    if request.action in {
        "participate",
        "participate_triple",
        "refresh_all",
        "refresh_source",
        "refresh_watch",
    }:
        if not is_llm_ready():
            raise HTTPException(status_code=401, detail="请先保存 LLM 配置并通过连接测试后再执行此操作")
    params = request.params or {}
    if request.action == "refresh_source":
        from web.actions import DS_HANDLER_BY_ID

        source_id = str(params.get("source_id") or "").strip()
        if source_id not in DS_HANDLER_BY_ID:
            raise HTTPException(status_code=400, detail="数据源 ID 无效")
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
        "participate_fallback_text": get_participate_fallback_text(),
        "default_participate_fallback_text": DEFAULT_PARTICIPATE_FALLBACK_TEXT,
        "participate_text_mode": get_participate_text_mode(),
        "default_participate_text_mode": DEFAULT_PARTICIPATE_TEXT_MODE,
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
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"保存 LLM 配置失败：{exc}") from exc
    logged_in = bool(account.get("logged_in"))
    return {
        "llm": llm,
        "setup_complete": logged_in and bool(llm.get("ready")),
    }


@app.put("/api/settings/participate-text")
@app.post("/api/settings/participate-text")
def api_update_participate_text(request: ParticipateTextRequest) -> dict[str, Any]:
    account = get_account_profile()
    if not account.get("logged_in"):
        raise HTTPException(status_code=401, detail="请先扫码登录后再修改参与文案")
    payload: dict[str, Any] = {}
    try:
        if request.participate_text_mode is not None:
            payload["participate_text_mode"] = set_participate_text_mode(request.participate_text_mode)
        if request.participate_text is not None:
            payload["participate_text"] = set_participate_text(request.participate_text)
        if request.participate_fallback_text is not None:
            payload["participate_fallback_text"] = set_participate_fallback_text(
                request.participate_fallback_text
            )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"保存参与文案失败：{exc}") from exc
    if not payload:
        raise HTTPException(status_code=400, detail="未提供可保存的设置")
    return payload


@app.put("/api/settings/participate-text-mode")
@app.post("/api/settings/participate-text-mode")
def api_update_participate_text_mode(request: ParticipateTextRequest) -> dict[str, str]:
    account = get_account_profile()
    if not account.get("logged_in"):
        raise HTTPException(status_code=401, detail="请先扫码登录后再修改参与文案模式")
    if request.participate_text_mode is None:
        raise HTTPException(status_code=400, detail="缺少 participate_text_mode")
    try:
        value = set_participate_text_mode(request.participate_text_mode)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"保存参与文案模式失败：{exc}") from exc
    return {"participate_text_mode": value}


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
    return FileResponse(
        QR_IMAGE_PATH,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@app.get("/app.js")
def api_app_js() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/styles.css")
def api_styles_css() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "styles.css",
        media_type="text/css",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
