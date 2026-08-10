"""API Pydantic schemas（请求/响应边界模型）。"""

from web.schemas.account import AccountSwitchRequest, AckAtUnreadRequest
from web.schemas.common import ErrorBody, ErrorObject, OkResponse
from web.schemas.diagnostics import DiagnosticsBundleOut, DiagnosticsLogsOut
from web.schemas.jobs import (
    ALLOWED_JOB_ACTIONS,
    JobRequest,
    JobStartOut,
    JobStatusOut,
)
from web.schemas.settings import LlmSettingsRequest, ParticipateTextRequest
from web.schemas.updates import UpdatesCheckOut
from web.schemas.watch import WatchUserRequest

__all__ = [
    "ALLOWED_JOB_ACTIONS",
    "AccountSwitchRequest",
    "AckAtUnreadRequest",
    "DiagnosticsBundleOut",
    "DiagnosticsLogsOut",
    "ErrorBody",
    "ErrorObject",
    "JobRequest",
    "JobStartOut",
    "JobStatusOut",
    "LlmSettingsRequest",
    "OkResponse",
    "ParticipateTextRequest",
    "UpdatesCheckOut",
    "WatchUserRequest",
]
