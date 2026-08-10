"""多账号池（源自 LAS 的 multiple_account 机制，适配 Binggo 常驻服务形态）。

文件布局（均在 config 目录下）：
- `accounts/{uid}.txt`  每个账号的 cookie 文本（secure 写入）
- `accounts/active`     当前活跃账号 uid（纯数字或空）

约定：**活跃账号始终镜像到 `config/cookies.txt`**，因此现有读取点
（`bilibili_auth` / `bilibili_client` / `account_service`）零改动；
切号 = 把目标账号 cookie 物化到 cookies.txt + 更新 active 文件。
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

from src import app_paths
from src.secure_files import write_text_secret

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
    """返回账号池列表：[{uid, active}]，按 uid 排序（纯读，无副作用）。"""
    _ensure_dir()
    with _lock:
        active_uid = _read_active_uid_locked()
        accounts: list[dict] = []
        for path in sorted(_accounts_dir().glob("*.txt")):
            uid_text = path.stem
            try:
                uid = int(uid_text)
            except (TypeError, ValueError):
                continue
            accounts.append({"uid": uid, "active": uid == active_uid})
        return accounts


def ensure_legacy_account() -> int | None:
    """旧版本单账号升级：池为空但 cookies.txt 可解析出 uid 时，自动登记为账号。

    显式调用（GET /api/accounts 前），保证 list_accounts 保持纯读。
    返回登记的 uid；无需登记返回 None。
    """
    with _lock:
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


def get_active_uid() -> int | None:
    with _lock:
        return _read_active_uid_locked()


def _write_active_locked(uid: int) -> None:
    _ensure_dir()
    _active_path().write_text(str(uid), encoding="utf-8")


def _materialize_cookie(cookie_str: str) -> None:
    """把 cookie 文本镜像到 config/cookies.txt（活跃账号）。"""
    _cookie_path().parent.mkdir(parents=True, exist_ok=True)
    write_text_secret(_cookie_path(), cookie_str)


def set_active(uid: int) -> bool:
    """切换活跃账号：账号不存在返回 False。"""
    with _lock:
        account_path = _accounts_dir() / f"{int(uid)}.txt"
        if not account_path.exists():
            return False
        cookie_str = account_path.read_text(encoding="utf-8", errors="replace").strip()
        if not cookie_str:
            return False
        _materialize_cookie(cookie_str)
        _write_active_locked(int(uid))
        return True


def register_login_cookie(cookie_str: str) -> int | None:
    """把新登录的 cookie 存入账号池并设为活跃；解析不出 uid 返回 None。"""
    cookie_str = (cookie_str or "").strip()
    uid = _uid_from_cookie(cookie_str)
    if uid is None:
        return None
    with _lock:
        _ensure_dir()
        account_path = _accounts_dir() / f"{uid}.txt"
        write_text_secret(account_path, cookie_str)
        _materialize_cookie(cookie_str)
        _write_active_locked(uid)
        return uid


def remove_account(uid: int) -> bool:
    """删除账号；删除的是活跃账号时清空 cookies.txt 与 active。"""
    with _lock:
        account_path = _accounts_dir() / f"{int(uid)}.txt"
        if not account_path.exists():
            return False
        try:
            account_path.unlink()
        except OSError:
            return False
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
