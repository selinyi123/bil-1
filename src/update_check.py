"""检查 GitHub Releases 是否有新版本（手动触发，无自动下载）。"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from src.log_redact import redact_text
from src.version_info import compare_versions, get_version, strip_v_prefix

GITHUB_REPO = "selinyi123/bil-1"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
TIMEOUT_SEC = 8.0
_NOTES_MAX = 500


@dataclass(frozen=True)
class UpdateCheckResult:
    ok: bool
    current: str
    latest: str | None
    update_available: bool
    release_url: str | None
    download_url: str | None
    notes_excerpt: str | None
    message: str
    error_kind: str | None
    platform: str
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_platform(platform: str | None = None) -> str:
    if platform in {"windows", "macos", "linux"}:
        return platform
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return "unknown"


def _platform_hint(platform: str) -> str:
    if platform == "windows":
        return "请下载 Binggo-Setup-win64.exe 或 Binggo-Portable-win64.zip"
    if platform == "macos":
        return "请下载 Binggo-macOS-arm64.dmg（推荐，拖到应用程序）或 Binggo-macOS-arm64.zip"
    return "请到 GitHub Releases 下载对应平台安装包"


def _pick_download_url(assets: list[Any], platform: str) -> str | None:
    names: list[tuple[str, str]] = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        url = str(item.get("browser_download_url") or "")
        if name and url:
            names.append((name.lower(), url))
    if platform == "windows":
        for key in ("setup-win64", "portable-win64", "win64"):
            for name, url in names:
                if key in name and name.endswith((".exe", ".zip")):
                    return url
    if platform == "macos":
        for key in ("macos-arm64", "macos", "darwin"):
            for name, url in names:
                if key in name and name.endswith(".dmg"):
                    return url
        for key in ("macos-arm64", "macos", "darwin"):
            for name, url in names:
                if key in name and name.endswith(".zip"):
                    return url
    return None


def _fail(
    *,
    current: str,
    plat: str,
    hint: str,
    message: str,
    error_kind: str,
    release_url: str | None = None,
) -> UpdateCheckResult:
    return UpdateCheckResult(
        ok=False,
        current=current,
        latest=None,
        update_available=False,
        release_url=release_url or GITHUB_RELEASES_PAGE,
        download_url=None,
        notes_excerpt=None,
        message=message,
        error_kind=error_kind,
        platform=plat,
        hint=hint,
    )


def check_for_updates(*, platform: str | None = None) -> UpdateCheckResult:
    current = get_version()
    plat = infer_platform(platform)
    hint = _platform_hint(plat)
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            resp = client.get(
                GITHUB_API_LATEST,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"Binggo/{current} (+local-console)",
                },
            )
            resp.raise_for_status()
            try:
                payload = resp.json()
            except (json.JSONDecodeError, ValueError):
                return _fail(
                    current=current,
                    plat=plat,
                    hint=hint,
                    message="无法解析 GitHub 返回内容",
                    error_kind="parse",
                )
    except httpx.TimeoutException:
        return _fail(
            current=current,
            plat=plat,
            hint=hint,
            message="检查更新超时，请稍后重试或手动打开 Releases",
            error_kind="network",
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        if status == 404:
            msg = "未找到公开 Release，请稍后在 GitHub Releases 查看"
        elif status in {403, 429}:
            msg = "GitHub 暂时限流，请稍后重试或手动打开 Releases"
        else:
            msg = "检查更新失败，请稍后重试或手动打开 Releases"
        return _fail(current=current, plat=plat, hint=hint, message=msg, error_kind="network")
    except httpx.HTTPError:
        return _fail(
            current=current,
            plat=plat,
            hint=hint,
            message="检查更新失败：网络异常，请稍后重试或手动打开 Releases",
            error_kind="network",
        )
    except Exception:
        return _fail(
            current=current,
            plat=plat,
            hint=hint,
            message="检查更新失败，请稍后重试或手动打开 Releases",
            error_kind="network",
        )

    if not isinstance(payload, dict):
        return _fail(
            current=current,
            plat=plat,
            hint=hint,
            message="无法解析 GitHub 返回内容",
            error_kind="parse",
        )

    tag = str(payload.get("tag_name") or "").strip()
    latest = strip_v_prefix(tag) if tag else None
    if latest == "":
        latest = None
    release_url = str(payload.get("html_url") or "").strip() or GITHUB_RELEASES_PAGE
    body = str(payload.get("body") or "").strip()
    notes = None
    if body:
        excerpt = body[:_NOTES_MAX] + ("…" if len(body) > _NOTES_MAX else "")
        notes = redact_text(excerpt)
    assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    download_url = _pick_download_url(assets, plat)

    if not latest:
        return UpdateCheckResult(
            ok=False,
            current=current,
            latest=None,
            update_available=False,
            release_url=release_url,
            download_url=download_url,
            notes_excerpt=notes,
            message="未找到有效的最新版本号",
            error_kind="empty",
            platform=plat,
            hint=hint,
        )

    cmp = compare_versions(current, latest)
    if cmp is None:
        return UpdateCheckResult(
            ok=True,
            current=current,
            latest=latest,
            update_available=False,
            release_url=release_url,
            download_url=download_url,
            notes_excerpt=notes,
            message=f"无法比较版本（当前 {current}，远端 {latest}），请手动查看 Releases",
            error_kind=None,
            platform=plat,
            hint=hint,
        )
    if cmp == -1:
        return UpdateCheckResult(
            ok=True,
            current=current,
            latest=latest,
            update_available=True,
            release_url=release_url,
            download_url=download_url,
            notes_excerpt=notes,
            message=f"发现新版本 {latest}",
            error_kind=None,
            platform=plat,
            hint=hint,
        )
    if cmp == 1:
        return UpdateCheckResult(
            ok=True,
            current=current,
            latest=latest,
            update_available=False,
            release_url=release_url,
            download_url=download_url,
            notes_excerpt=notes,
            message=f"当前版本 {current} 新于远端 {latest}",
            error_kind=None,
            platform=plat,
            hint=hint,
        )
    return UpdateCheckResult(
        ok=True,
        current=current,
        latest=latest,
        update_available=False,
        release_url=release_url,
        download_url=download_url,
        notes_excerpt=notes,
        message="已是最新版本",
        error_kind=None,
        platform=plat,
        hint=hint,
    )
