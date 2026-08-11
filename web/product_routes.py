"""Settings / Data Sources 正式产品路由。

与历史 /api/settings/enhance/notify 分离：这里仅负责新的 typed source settings
和账号级 Proxy。数据源配置属于本地控制面，不要求 B 站登录；Proxy 是账号级配置，
必须绑定有效账号。所有 mutation 在 Job 运行中 fail-closed，避免任务执行期间改变
数据源/网络上下文。
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, FastAPI

from src.account_pool import (
    accounts_dir_has,
    ensure_legacy_account,
    get_account_proxy,
    set_account_proxy,
)
from src.bilibili_auth import resolve_effective_uid
from src.proxy_config import get_env_proxy_url, get_global_proxy_url
from src.source_settings import (
    add_ds10_source,
    get_source_settings_payload,
    remove_ds10_source,
    set_ds8_dynamic_ids,
    set_ds9_tags,
)
from web.account_service import get_account_profile
from web.api_errors import AppError, ErrorCode, require_login
from web.job_runner import runner
from web.schemas.product_settings import (
    AccountProxyRequest,
    Ds10SourceRequest,
    Ds8SettingsRequest,
    Ds9SettingsRequest,
)

router = APIRouter()


def _require_local_account() -> int:
    account = get_account_profile()
    require_login(account, message="请先扫码登录后再修改账号级设置")
    ensure_legacy_account()
    uid = resolve_effective_uid()
    if not uid:
        raise AppError(ErrorCode.AUTH_REQUIRED, "未检测到有效账号身份")
    return int(uid)


def _reject_mutation_while_job_running() -> None:
    if runner.is_running():
        raise AppError(
            ErrorCode.JOB_BUSY,
            "有任务正在运行，请等待任务结束后再修改数据源或网络设置",
        )


def _mask_proxy_url(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port else ""
        auth = "***@" if parsed.username is not None or parsed.password is not None else ""
        return urlunsplit((parsed.scheme, f"{auth}{host}{port}", parsed.path, "", ""))
    except ValueError:
        return "***"


def _validate_proxy_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("代理地址不能为空")
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("账号级代理仅支持 http:// 或 https://")
    if not parsed.hostname:
        raise ValueError("代理地址缺少主机名")
    try:
        if parsed.port is not None and not (1 <= parsed.port <= 65535):
            raise ValueError("代理端口必须在 1~65535")
    except ValueError as exc:
        raise ValueError("代理端口无效") from exc
    return raw


def _proxy_payload(uid: int) -> dict:
    env_proxy = get_env_proxy_url()
    account_proxy = get_account_proxy(uid)
    global_proxy = get_global_proxy_url()
    effective = env_proxy or account_proxy or global_proxy
    if env_proxy:
        source = "environment"
    elif account_proxy:
        source = "account"
    elif global_proxy:
        source = "global"
    else:
        source = "none"
    return {
        "ok": True,
        "uid": uid,
        "editable": accounts_dir_has(uid),
        "effective_source": source,
        "effective_proxy": _mask_proxy_url(effective),
        "env_override": bool(env_proxy),
        "account_configured": bool(account_proxy),
        "account_proxy": _mask_proxy_url(account_proxy),
        "global_configured": bool(global_proxy),
        "global_proxy": _mask_proxy_url(global_proxy),
    }


@router.get("/api/source-settings", tags=["data-sources"])
def api_source_settings() -> dict:
    return {"ok": True, **get_source_settings_payload()}


@router.put("/api/source-settings/ds8", tags=["data-sources"])
def api_update_ds8(request: Ds8SettingsRequest) -> dict:
    _reject_mutation_while_job_running()
    try:
        values = set_ds8_dynamic_ids(request.dynamic_ids)
    except (ValueError, OSError) as exc:
        code = ErrorCode.VALIDATION_ERROR if isinstance(exc, ValueError) else ErrorCode.INTERNAL
        raise AppError(code, str(exc) or "保存 DS-8 失败") from exc
    return {"ok": True, "ds8": {"dynamic_ids": values, "count": len(values)}}


@router.put("/api/source-settings/ds9", tags=["data-sources"])
def api_update_ds9(request: Ds9SettingsRequest) -> dict:
    _reject_mutation_while_job_running()
    try:
        values = set_ds9_tags(request.tags)
    except (ValueError, OSError) as exc:
        code = ErrorCode.VALIDATION_ERROR if isinstance(exc, ValueError) else ErrorCode.INTERNAL
        raise AppError(code, str(exc) or "保存 DS-9 失败") from exc
    return {"ok": True, "ds9": {"tags": values, "count": len(values)}}


@router.post("/api/source-settings/ds10", tags=["data-sources"])
def api_add_ds10(request: Ds10SourceRequest) -> dict:
    _reject_mutation_while_job_running()
    try:
        entry = add_ds10_source(request.source)
    except (ValueError, OSError) as exc:
        code = ErrorCode.VALIDATION_ERROR if isinstance(exc, ValueError) else ErrorCode.INTERNAL
        raise AppError(code, str(exc) or "添加 DS-10 外部源失败") from exc
    return {"ok": True, "entry": entry, "ds10": get_source_settings_payload()["ds10"]}


@router.delete("/api/source-settings/ds10/{source_id}", tags=["data-sources"])
def api_remove_ds10(source_id: str) -> dict:
    _reject_mutation_while_job_running()
    try:
        removed = remove_ds10_source(source_id)
    except OSError as exc:
        raise AppError(ErrorCode.INTERNAL, f"删除 DS-10 外部源失败：{exc}") from exc
    if not removed:
        raise AppError(ErrorCode.NOT_FOUND, "DS-10 外部源不存在")
    return {"ok": True, "ds10": get_source_settings_payload()["ds10"]}


@router.get("/api/settings/proxy", tags=["settings"])
def api_get_account_proxy() -> dict:
    uid = _require_local_account()
    return _proxy_payload(uid)


@router.put("/api/settings/proxy", tags=["settings"])
def api_update_account_proxy(request: AccountProxyRequest) -> dict:
    uid = _require_local_account()
    _reject_mutation_while_job_running()
    if not accounts_dir_has(uid):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "当前身份由环境变量管理，尚未登记到账号池，无法保存账号级代理",
        )
    try:
        if request.clear:
            ok = set_account_proxy(uid, None)
        else:
            ok = set_account_proxy(uid, _validate_proxy_url(str(request.proxy or "")))
    except ValueError as exc:
        raise AppError(ErrorCode.VALIDATION_ERROR, str(exc)) from exc
    except OSError as exc:
        raise AppError(ErrorCode.INTERNAL, f"保存账号级代理失败：{exc}") from exc
    if not ok:
        raise AppError(ErrorCode.NOT_FOUND, f"账号 {uid} 不在账号池中")
    return _proxy_payload(uid)


def install_product_routes(app: FastAPI) -> None:
    """显式安装新架构路由；app.py 只需调用一次。"""
    app.include_router(router)
