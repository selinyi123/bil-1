"""统一 API 错误码、AppError 与异常处理器。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from src.app_logging import get_logger
from src.llm_settings import is_llm_ready
from web.user_messages import friendly_error

logger = get_logger("api")


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    LLM_NOT_READY = "LLM_NOT_READY"
    NOT_FOUND = "NOT_FOUND"
    JOB_BUSY = "JOB_BUSY"
    JOB_NOT_CANCELLABLE = "JOB_NOT_CANCELLABLE"
    AUTO_ALREADY_RUNNING = "AUTO_ALREADY_RUNNING"
    INTERNAL = "INTERNAL"


ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.UNSUPPORTED_ACTION: 400,
    ErrorCode.AUTH_REQUIRED: 401,
    ErrorCode.LLM_NOT_READY: 401,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.JOB_BUSY: 409,
    ErrorCode.JOB_NOT_CANCELLABLE: 409,
    ErrorCode.AUTO_ALREADY_RUNNING: 409,
    ErrorCode.INTERNAL: 500,
}

ERROR_CATALOG: dict[str, dict[str, Any]] = {
    code.value: {"http": ERROR_HTTP_STATUS[code], "code": code.value} for code in ErrorCode
}


def _coerce_error_code(code: ErrorCode | str) -> ErrorCode:
    if isinstance(code, ErrorCode):
        return code
    try:
        return ErrorCode(str(code))
    except ValueError:
        logger.warning("未知错误码 %r，回退 INTERNAL", code)
        return ErrorCode.INTERNAL


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        *,
        status_code: int | None = None,
        detail: Any = None,
    ) -> None:
        code_enum = _coerce_error_code(code)
        text = str(message or "").strip() or "操作失败，请稍后重试"
        self.code = code_enum
        self.message = text
        self.detail = detail
        self.status_code = int(status_code or ERROR_HTTP_STATUS[code_enum])
        super().__init__(text)


def build_error_payload(code: str, message: str, detail: Any = None) -> dict[str, Any]:
    text = str(message or "").strip() or "操作失败，请稍后重试"
    return {
        "error": {
            "code": str(code),
            "message": text,
            "detail": detail,
        },
        "detail": text,
    }


def error_response(
    *,
    code: ErrorCode | str,
    message: str,
    status_code: int,
    detail: Any = None,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content=build_error_payload(str(code), message, detail),
    )
    return response


def require_login(account: dict[str, Any], *, message: str = "请先扫码登录后再执行此操作") -> None:
    if not account.get("logged_in"):
        raise AppError(ErrorCode.AUTH_REQUIRED, message)


def require_llm_ready(
    *,
    message: str = "请先保存 LLM 配置并通过连接测试后再执行此操作",
) -> None:
    if not is_llm_ready():
        raise AppError(ErrorCode.LLM_NOT_READY, message)


def _http_exception_to_code(status_code: int, message: str) -> ErrorCode:
    if status_code == 401:
        if "LLM" in message or "连接测试" in message:
            return ErrorCode.LLM_NOT_READY
        return ErrorCode.AUTH_REQUIRED
    if status_code == 404:
        return ErrorCode.NOT_FOUND
    if status_code == 409:
        if "没有可取消" in message or "可取消" in message:
            return ErrorCode.JOB_NOT_CANCELLABLE
        if "调度" in message and "运行" in message:
            return ErrorCode.AUTO_ALREADY_RUNNING
        return ErrorCode.JOB_BUSY
    if status_code >= 500:
        return ErrorCode.INTERNAL
    return ErrorCode.VALIDATION_ERROR


def _normalize_validation_errors(errors: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in errors:
        if not isinstance(item, dict):
            continue
        loc = item.get("loc") or ()
        normalized.append(
            {
                "loc": list(loc),
                "msg": str(item.get("msg") or "invalid"),
                "type": str(item.get("type") or "value_error"),
            }
        )
    return normalized


def _validation_user_message(details: list[dict[str, Any]]) -> str:
    if not details:
        return "请求参数无效"
    msg = str(details[0].get("msg") or "").strip()
    if msg.startswith("Value error, "):
        msg = msg[len("Value error, ") :].strip()
    lowered = msg.lower()
    if not msg or lowered in {"field required", "missing"} or (
        "required" in lowered and "field" in lowered
    ):
        return "请求参数无效"
    return msg


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            detail=exc.detail,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = _normalize_validation_errors(list(exc.errors()))
        return error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message=_validation_user_message(details),
            status_code=400,
            detail=details or None,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        raw = exc.detail
        if isinstance(raw, str):
            message = raw.strip() or "请求失败"
            detail: Any = None
        else:
            message = "请求失败"
            detail = raw
        code = _http_exception_to_code(int(exc.status_code), message)
        return error_response(
            code=code,
            message=message,
            status_code=int(exc.status_code),
            detail=detail,
        )

    @app.exception_handler(ClientDisconnect)
    async def client_disconnect_handler(_request: Request, _exc: ClientDisconnect) -> Response:
        # 客户端已断开，勿再写 JSON 错误体
        return Response(status_code=204)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        # 防御性：部分环境 ClientDisconnect 可能未命中专用 handler
        if isinstance(exc, ClientDisconnect):
            return Response(status_code=204)
        logger.exception("未捕获 API 异常: %s", type(exc).__name__)
        return error_response(
            code=ErrorCode.INTERNAL,
            message=friendly_error(exc),
            status_code=500,
            detail=None,
        )


def patch_openapi_schema(schema: dict) -> dict:
    """在 OpenAPI 中补齐统一错误体（ErrorObject / ErrorBody）定义。"""
    info = schema.setdefault("info", {})
    description = str(info.get("description") or "").strip()
    error_note = "失败响应统一为 ErrorBody（error.code / error.message / detail）。"
    if error_note not in description:
        info["description"] = f"{description}\n\n{error_note}".strip()

    components = schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    schemas.setdefault(
        "ErrorObject",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
                "detail": {},
            },
            "required": ["code", "message"],
        },
    )
    schemas.setdefault(
        "ErrorBody",
        {
            "type": "object",
            "properties": {
                "error": {"$ref": "#/components/schemas/ErrorObject"},
                "detail": {
                    "type": "string",
                    "description": "兼容字段，等于 error.message",
                },
            },
            "required": ["error", "detail"],
        },
    )
    return schema
