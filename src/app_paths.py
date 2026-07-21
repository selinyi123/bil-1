"""应用安装目录与用户数据目录（支持开发模式与 PyInstaller 打包）。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

__version__ = "5.0.1"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_root() -> Path:
    """代码与内置资源目录（开发时为仓库根；打包后为 PyInstaller 解压目录）。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[1]


def app_bundle_root() -> Path:
    """返回 Xxx.app 目录；非 .app 结构则退回可执行文件所在目录。"""
    exe = Path(sys.executable).resolve()
    # .../Binggo.app/Contents/MacOS/Binggo
    if len(exe.parts) >= 3 and exe.parts[-2] == "MacOS" and exe.parts[-3] == "Contents":
        return exe.parents[2]
    return exe.parent


def bundle_root() -> Path:
    """可执行文件所在目录（便携版相关路径计算的基础）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def platform_label() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return "unknown"


def user_home() -> Path:
    """用户数据根目录（config/、data/）。"""
    override = os.environ.get("BINGGO_HOME", "").strip()
    if override:
        return Path(override)
    if is_frozen():
        portable = os.environ.get("BINGGO_PORTABLE", "").strip().lower() in {"1", "true", "yes"}
        if portable:
            if sys.platform == "darwin":
                # 解压目录（Binggo.app 的父目录）
                return app_bundle_root().parent
            return bundle_root()
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "Binggo"
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / "Binggo"
        return Path.home() / "Binggo"
    return Path(__file__).resolve().parents[1]


def config_dir() -> Path:
    return user_home() / "config"


def data_dir() -> Path:
    return user_home() / "data"


def cookie_file() -> Path:
    """动态解析 cookies.txt（尊重当前 BINGGO_HOME）。"""
    return config_dir() / "cookies.txt"


def llm_env_file() -> Path:
    """动态解析 llm.env（尊重当前 BINGGO_HOME）。"""
    return config_dir() / "llm.env"


INSTALL_ROOT = install_root()
USER_HOME = user_home()
DATA_DIR = USER_HOME / "data"
CONFIG_DIR = USER_HOME / "config"
COOKIE_PATH = CONFIG_DIR / "cookies.txt"
LLM_ENV_PATH = CONFIG_DIR / "llm.env"
WATCH_USERS_PATH = CONFIG_DIR / "watch_users.json"
WATCH_CANDIDATES_PATH = CONFIG_DIR / "watch_users_candidates.json"
GLOBAL_SETTINGS_PATH = CONFIG_DIR / "participate_settings.json"
QR_IMAGE_PATH = DATA_DIR / "login_qrcode.png"
ACCOUNT_CACHE_PATH = DATA_DIR / "cache" / "account_profile.json"

_SEEDED = False
_BOOTSTRAPPED = False


def _bootstrap_user_data() -> None:
    """首次安装引导：无内置种子时保持空库（由用户自行更新数据源）。"""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    from src.activity_store import seed_activities_if_empty
    from src.state_store import seed_state_if_missing

    # 发行版不再打包 activities_seed / state_seed；有本地可选种子时才灌入
    seed_state_if_missing()
    seed_activities_if_empty()
    _BOOTSTRAPPED = True


def ensure_user_dirs() -> None:
    """创建用户目录，并从安装包复制配置模板（仅首次）。

    顺序：mkdir → 复制模板 → init_db → 标记已就绪 → 种子数据。
    先置 `_SEEDED` 再 seed，避免 seed 内再次调用本函数时递归 bootstrap。
    """
    global _SEEDED
    home = user_home()
    data_dir = home / "data"
    config_dir = home / "config"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "output").mkdir(parents=True, exist_ok=True)
    (data_dir / "cache").mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)

    if not _SEEDED:
        bundled_config = install_root() / "config"
        if bundled_config.is_dir():
            for item in bundled_config.iterdir():
                if not item.is_file():
                    continue
                if item.name.endswith(".example"):
                    dst = config_dir / item.name
                    if not dst.exists():
                        shutil.copy2(item, dst)
                    continue
                if item.name == "sources.yaml":
                    dst = config_dir / item.name
                    if not dst.exists():
                        shutil.copy2(item, dst)
        from src.db import init_db

        init_db()
        _SEEDED = True
        _bootstrap_user_data()


def runtime_label() -> str:
    """按当前环境动态计算（勿依赖导入时 USER_HOME 快照）。"""
    if is_frozen():
        portable = os.environ.get("BINGGO_PORTABLE", "").strip().lower() in {"1", "true", "yes"}
        if portable:
            return "portable"
        return "installed"
    return "dev"
