"""启动配置自检（D1）：软警告，不阻断启动。"""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

from src.app_logging import get_logger
from src.app_paths import __version__, platform_label, runtime_label, user_home
from src.config_validate import cookie_has_dede_user_id, cookie_missing_hard_fields
from src.dashboard_server import DASHBOARD_HOST, get_dashboard_port
from src.secrets_inventory import secret_filenames_csv

logger = get_logger("config")

_LOGGED = False
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class HealthFinding:
    code: str
    severity: str
    message: str
    path: str | None = None


@dataclass(frozen=True)
class HealthReport:
    runtime: str
    user_home: str
    data_dir: str
    config_dir: str
    version: str
    bind_host: str
    bind_port: int
    platform: str = "unknown"
    findings: list[HealthFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _perms_too_open(path: Any) -> bool:
    if sys.platform == "win32":
        return False
    try:
        mode = path.stat().st_mode
    except OSError:
        # 检查不了不等于没问题：按"疑似过宽"上报，避免漏报密钥暴露。
        return True
    return bool(mode & (stat.S_IRGRP | stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH))


def run_config_health_checks() -> HealthReport:
    from src import app_paths

    findings: list[HealthFinding] = []
    cookie_path = app_paths.cookie_file()
    llm_path = app_paths.llm_env_file()

    if os.environ.get("BILI_COOKIE", "").strip():
        findings.append(
            HealthFinding(
                code="env_cookie_override",
                severity="warning",
                message="检测到 BILI_COOKIE 环境变量，登录态可能来自环境变量而非 cookies.txt",
            )
        )

    # 与 load_llm_config 一致：三者皆非空才真正覆盖文件
    if all(os.environ.get(name, "").strip() for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME")):
        findings.append(
            HealthFinding(
                code="env_llm_override",
                severity="warning",
                message="检测到完整 LLM_* 环境变量，LLM 配置正使用环境变量而非 llm.env",
            )
        )

    if sys.platform == "win32":
        # harden_file_permissions() 在 Windows 上是 no-op；如实告知，不假装已收紧。
        for path in (cookie_path, llm_path):
            if path.is_file():
                findings.append(
                    HealthFinding(
                        code="secret_file_perms_unenforced",
                        severity="info",
                        message=f"Windows 平台未收紧密钥文件权限：{path.name}（同机其他用户可能可读）",
                        path=str(path),
                    )
                )
    else:
        for path in (cookie_path, llm_path):
            if path.is_file() and _perms_too_open(path):
                findings.append(
                    HealthFinding(
                        code="secret_file_perms",
                        severity="warning",
                        message=f"密钥文件权限可能过宽：{path.name}",
                        path=str(path),
                    )
                )

    if cookie_path.is_file():
        try:
            cookie_text = cookie_path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(
                HealthFinding(
                    code="cookie_unreadable",
                    severity="warning",
                    message=f"无法读取 cookies.txt：{exc}",
                    path=str(cookie_path),
                )
            )
        else:
            missing = cookie_missing_hard_fields(cookie_text)
            if missing:
                findings.append(
                    HealthFinding(
                        code="cookie_missing_fields",
                        severity="warning",
                        message=f"cookies.txt 缺少字段：{', '.join(missing)}，建议重新扫码登录",
                        path=str(cookie_path),
                    )
                )
            elif cookie_text.strip() and not cookie_has_dede_user_id(cookie_text):
                findings.append(
                    HealthFinding(
                        code="cookie_missing_dede",
                        severity="info",
                        message="cookies.txt 未含 DedeUserID（可继续使用，建议重新扫码以补齐）",
                        path=str(cookie_path),
                    )
                )

    if llm_path.is_file():
        try:
            from src.llm_config import _parse_env_file_raw
            from src.llm_settings import _resolve_base_url

            raw = _parse_env_file_raw(llm_path)
            base_raw = (raw.get("LLM_BASE_URL") or "").strip()
            if base_raw:
                _resolve_base_url(base_raw)
        except ValueError as exc:
            findings.append(
                HealthFinding(
                    code="llm_env_invalid",
                    severity="warning",
                    message=f"llm.env 中的接口地址无效：{exc}",
                    path=str(llm_path),
                )
            )
        except OSError as exc:
            findings.append(
                HealthFinding(
                    code="llm_env_unreadable",
                    severity="warning",
                    message=f"无法读取 llm.env：{exc}",
                    path=str(llm_path),
                )
            )

    if DASHBOARD_HOST not in _LOOPBACK_HOSTS:
        findings.append(
            HealthFinding(
                code="bind_host_not_loopback",
                severity="error",
                message=f"绑定地址非 loopback：{DASHBOARD_HOST}",
            )
        )

    home = user_home()
    return HealthReport(
        runtime=runtime_label(),
        user_home=str(home),
        data_dir=str(home / "data"),
        config_dir=str(home / "config"),
        version=__version__,
        bind_host=DASHBOARD_HOST,
        bind_port=get_dashboard_port(),
        platform=platform_label(),
        findings=findings,
    )


def log_config_health(report: HealthReport | None = None, *, force: bool = False) -> HealthReport:
    """写启动自检日志；默认进程内只刷一次，避免 TestClient 重复刷屏。"""
    global _LOGGED
    result = report or run_config_health_checks()
    if _LOGGED and not force:
        return result
    _LOGGED = True
    logger.info(
        "配置自检 runtime=%s home=%s data=%s secrets_excluded=%s",
        result.runtime,
        result.user_home,
        result.data_dir,
        secret_filenames_csv(),
    )
    for item in result.findings:
        line = f"[{item.code}] {item.message}"
        if item.path:
            line = f"{line} path={item.path}"
        if item.severity == "error":
            logger.error("%s", line)
        elif item.severity == "warning":
            logger.warning("%s", line)
        else:
            logger.info("%s", line)
    return result


def reset_config_health_log_flag_for_tests() -> None:
    global _LOGGED
    _LOGGED = False
