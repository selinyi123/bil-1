"""多账号池（源自 LAS 的 multiple_account 机制，适配 Binggo 常驻服务形态）。

文件布局（均在 config 目录下）：
- `accounts/{uid}.txt`  每个账号的 cookie 文本（secure 写入）
- `accounts/active`     当前活跃账号 uid（纯数字或空）

约定：**活跃账号始终镜像到 `config/cookies.txt`**，因此现有读取点
（`bilibili_auth` / `bilibili_client` / `account_service`）零改动；
切号 = 把目标账号 cookie 物化到 cookies.txt + 更新 active 文件。
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from src import app_paths
from src.app_logging import get_logger
from src.secure_files import write_text_secret

logger = get_logger("account_pool")

_UID_RE = re.compile(r"DedeUserID=(\d+)")
_lock = threading.RLock()


def _accounts_dir() -> Path:
    return app_paths.accounts_dir()


def _active_path() -> Path:
    return app_paths.active_uid_file()


def _cookie_path() -> Path:
    return app_paths.cookie_file()


def _uid_from_cookie(cookie_str: str) -> int | None:
    match = _UID_RE.search(cookie_str or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _ensure_dir() -> None:
    _accounts_dir().mkdir(parents=True, exist_ok=True)


def list_accounts() -> list[dict]:
    """返回账号池列表：[{uid, active}]，按 uid 排序（纯读，无副作用，不创建目录）。

    active 标记基于生效身份（`BILI_COOKIE` env > 活跃账号），保证 UI 账号列表
    与顶部身份显示一致（P1 #3）。
    """
    with _lock:
        effective_uid = get_active_uid()
        accounts: list[dict] = []
        for path in sorted(_accounts_dir().glob("*.txt")):
            uid_text = path.stem
            try:
                uid = int(uid_text)
            except (TypeError, ValueError):
                continue
            accounts.append({"uid": uid, "active": uid == effective_uid})
        return accounts


def ensure_legacy_account() -> int | None:
    """旧版本单账号升级：池为空但 cookies.txt 可解析出 uid 时，自动登记为账号。

    BILI_COOKIE env 生效时不收养：此时 cookies.txt 是影子身份（实际请求
    用 env cookie），登记只会产生永远无法切换/使用的旧账号噪音。

    显式调用（GET /api/accounts 前），保证 list_accounts 保持纯读。
    返回登记的 uid；无需登记返回 None。
    """
    with _lock:
        if os.environ.get("BILI_COOKIE", "").strip():
            return None
        if list_accounts():
            return None
        cookie_text = _cookie_path().read_text(encoding="utf-8", errors="replace").strip() if _cookie_path().exists() else ""
        uid = _uid_from_cookie(cookie_text)
        if uid is not None and not accounts_dir_has(uid):
            return register_login_cookie(cookie_text)
        return None


def accounts_dir_has(uid: int) -> bool:
    return (_accounts_dir() / f"{int(uid)}.txt").exists()


def _read_active_uid_locked() -> int | None:
    path = _active_path()
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def pool_active_uid() -> int | None:
    """账号池活跃账号（config/accounts/active 文件）的 uid；无活跃账号返回 None。

    仅反映池状态，不包含 BILI_COOKIE 环境变量覆盖（那是 effective 身份，见
    `get_active_uid` / `src.bilibili_auth.resolve_effective_uid`）。
    """
    with _lock:
        return _read_active_uid_locked()


def get_active_uid() -> int | None:
    """当前生效身份 uid（UI 展示与实际请求身份一致）：

    `BILI_COOKIE` 环境变量 > 账号池活跃账号 > cookies.txt（P1 #3）。
    """
    from src.bilibili_auth import resolve_effective_uid

    return resolve_effective_uid()


def _write_active_locked(uid: int) -> None:
    _ensure_dir()
    _active_path().write_text(str(uid), encoding="utf-8")


def _materialize_cookie(cookie_str: str) -> None:
    """把 cookie 文本镜像到 config/cookies.txt（活跃账号）。"""
    _cookie_path().parent.mkdir(parents=True, exist_ok=True)
    write_text_secret(_cookie_path(), cookie_str)


def set_active(uid: int) -> bool:
    """切换活跃账号：账号不存在返回 False。

    `BILI_COOKIE` 环境变量生效时拒绝切换（env 显式覆盖身份，避免 UI 显示与
    实际请求身份再次分裂），返回 False 并记录警告。

    原子性加固：先写 cookies.txt（实际请求身份），再写 active（UI 身份）。
    active 写失败时回滚 cookies.txt 到旧值，避免"实际请求 UID != UI UID"
    的 I/O 部分失败窗口重新出现。
    """
    with _lock:
        if os.environ.get("BILI_COOKIE", "").strip():
            logger.warning(
                "BILI_COOKIE 环境变量覆盖当前身份，拒绝切换账号到 %s（如需切换请先移除环境变量）",
                uid,
            )
            return False
        account_path = _accounts_dir() / f"{int(uid)}.txt"
        if not account_path.exists():
            return False
        cookie_str = account_path.read_text(encoding="utf-8", errors="replace").strip()
        if not cookie_str:
            return False
        old_cookie = (
            _cookie_path().read_text(encoding="utf-8", errors="replace").strip()
            if _cookie_path().exists()
            else None
        )
        try:
            _materialize_cookie(cookie_str)
            _write_active_locked(int(uid))
        except OSError:
            # 回滚：恢复旧 cookie（尽力而为），保持 cookies.txt 与 active 一致
            try:
                if old_cookie:
                    _materialize_cookie(old_cookie)
                else:
                    _cookie_path().unlink(missing_ok=True)
            except OSError:
                pass
            return False
        return True


def register_login_cookie(cookie_str: str) -> int | None:
    """把新登录的 cookie 存入账号池并设为活跃；解析不出 uid 返回 None。

    `BILI_COOKIE` 环境变量生效时仅登记账号（写入 {uid}.txt），不切换活跃、
    不镜像 cookies.txt——env 显式覆盖身份，避免登录后 UI 显示与实际身份分裂。

    与 set_active 相同的原子性加固：active 写失败时回滚 cookies.txt。
    """
    cookie_str = (cookie_str or "").strip()
    uid = _uid_from_cookie(cookie_str)
    if uid is None:
        return None
    env_override = bool(os.environ.get("BILI_COOKIE", "").strip())
    with _lock:
        _ensure_dir()
        account_path = _accounts_dir() / f"{uid}.txt"
        write_text_secret(account_path, cookie_str)
        if env_override:
            logger.warning(
                "BILI_COOKIE 环境变量覆盖当前身份，登录账号 %s 仅登记、不切换活跃",
                uid,
            )
            return uid
        old_cookie = (
            _cookie_path().read_text(encoding="utf-8", errors="replace").strip()
            if _cookie_path().exists()
            else None
        )
        try:
            _materialize_cookie(cookie_str)
            _write_active_locked(uid)
        except OSError:
            try:
                if old_cookie:
                    _materialize_cookie(old_cookie)
                else:
                    _cookie_path().unlink(missing_ok=True)
            except OSError:
                pass
            return None
        return uid


def remove_account(uid: int) -> bool:
    """删除账号（凭据 + 账号级 proxy metadata）；删除的是活跃账号时清空 cookies.txt 与 active。

    保留参与历史与本地活动库（"删除账号" = 移除凭据与账号专属配置，
    不销毁历史数据；账号重新登录后历史仍可追溯）。
    """
    with _lock:
        account_path = _accounts_dir() / f"{int(uid)}.txt"
        if not account_path.exists():
            return False
        try:
            account_path.unlink()
        except OSError:
            return False
        # 清理账号级 proxy metadata（accounts/{uid}.json），避免重新登录后旧代理复活
        try:
            _account_meta_path(uid).unlink(missing_ok=True)
        except OSError:
            pass
        active_uid = _read_active_uid_locked()
        if active_uid == int(uid):
            _cookie_path().unlink(missing_ok=True)
            _active_path().unlink(missing_ok=True)
        return True


def clear_active() -> None:
    """退出登录：清除活跃标记与 cookies.txt，保留账号池内其他账号。"""
    with _lock:
        _cookie_path().unlink(missing_ok=True)
        _active_path().unlink(missing_ok=True)


def account_count() -> int:
    return len(list_accounts())


# ----------------------------------------------------------------------
# 账号级代理（P1 #15）：config/accounts/{uid}.json，可选字段 {"proxy": "http://..."}
# ----------------------------------------------------------------------


def _account_meta_path(uid: int) -> Path:
    return _accounts_dir() / f"{int(uid)}.json"


def get_account_proxy(uid: int | None) -> str | None:
    """读取账号级代理：config/accounts/{uid}.json 的 proxy 字段；未配置返回 None。

    uid 为 None 时直接返回 None（无账号级概念）。
    """
    if uid is None:
        return None
    path = _account_meta_path(uid)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    proxy = str(data.get("proxy") or "").strip()
    return proxy or None


def set_account_proxy(uid: int, proxy: str | None) -> bool:
    """设置账号级代理（写入 config/accounts/{uid}.json 的 proxy 字段）。

    proxy 为空或 None 表示清除（删除元数据文件）。账号不存在返回 False。
    """
    with _lock:
        if not accounts_dir_has(uid):
            return False
        _ensure_dir()
        path = _account_meta_path(uid)
        proxy = str(proxy).strip() if proxy is not None else ""
        if proxy:
            write_text_secret(
                path,
                json.dumps({"proxy": proxy}, ensure_ascii=False, indent=2),
            )
        else:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # 删除失败时写入空配置兜底，保证下次读取不再命中旧值
                write_text_secret(path, json.dumps({"proxy": ""}, ensure_ascii=False))
        return True
