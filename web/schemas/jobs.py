from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from web.api_errors import AppError, ErrorCode

ALLOWED_JOB_ACTIONS = frozenset(
    {
        "login",
        "refresh_all",
        "refresh_source",
        "refresh_watch",
        "refresh_status",
        "participate",
        "participate_triple",
        "check_prize",
        "clear_follows",
    }
)


# ---------- P2 #26：JobRequest.params 按 action 强类型校验 ----------
# extra="allow"：兼容现有前端可能多传的字段（校验不拒绝，且原样保留透传）。


class _RefreshSourceParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_id: str


class _ParticipateParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    dynamic_id: str
    push: bool | None = None


class _ParticipateTripleParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    # 宽松：筛选字段均按字符串处理，与 web/actions._list_filter_params 一致
    status: str | None = None
    lottery_type: str | None = None
    type: str | None = None
    draw: str | None = None
    draw_window: str | None = None
    q: str | None = None
    sort: str | None = None
    order: str | None = None
    from_auto: bool | None = None


class _ClearFollowsParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_days: int | None = Field(default=None, ge=1, le=365)
    delete_dynamic: bool | None = None
    white_list: str | None = None
    dry_run: bool | None = None


class _CheckPrizeParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    push: bool | None = None


class _EmptyParams(BaseModel):
    """无参数 action（login/refresh_all/refresh_watch/refresh_status）。"""

    model_config = ConfigDict(extra="allow")


_PARAM_MODELS: dict[str, type[BaseModel]] = {
    "refresh_source": _RefreshSourceParams,
    "participate": _ParticipateParams,
    "participate_triple": _ParticipateTripleParams,
    "clear_follows": _ClearFollowsParams,
    "check_prize": _CheckPrizeParams,
    "refresh_all": _EmptyParams,
    "refresh_watch": _EmptyParams,
    "refresh_status": _EmptyParams,
    "login": _EmptyParams,
}


def validate_job_params(action: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """按 action 校验并规范化 JobRequest.params。

    已知 action 用对应 Pydantic 模型校验（extra 字段保留透传）；
    未知 action 直接透传，由上层 ALLOWED_JOB_ACTIONS 决定是否拒绝。
    校验失败抛 AppError(ErrorCode.VALIDATION_ERROR)，消息含具体字段。
    """
    model = _PARAM_MODELS.get(action)
    if model is None:
        return dict(params or {})
    raw = params if isinstance(params, dict) else {}
    try:
        validated = model.model_validate(raw)
    except ValidationError as exc:
        details = exc.errors()
        if details:
            field = details[0].get("loc") or ()
            field_name = ".".join(str(part) for part in field) or "params"
            reason = str(details[0].get("msg") or "参数无效")
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"参数 {field_name} 无效：{reason}",
            ) from exc
        raise AppError(ErrorCode.VALIDATION_ERROR, "请求参数无效") from exc
    base = validated.model_dump(exclude_none=True)
    extra = dict(validated.model_extra or {})
    return {**base, **extra}


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
