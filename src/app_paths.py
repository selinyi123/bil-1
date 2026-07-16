"""应用安装目录与用户数据目录（支持开发模式与 PyInstaller 打包）。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

__version__ = "3.0.5"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_root() -> Path:
    """代码与内置资源目录（开发时为仓库根；打包后为 PyInstaller 解压目录）。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[1]


def bundle_root() -> Path:
    """可执行文件所在目录（便携版数据可放此处）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def user_home() -> Path:
    """用户数据根目录（config/、data/）。"""
    override = os.environ.get("BINGGO_HOME", "").strip()
    if override:
        return Path(override)
    if is_frozen():
        portable = os.environ.get("BINGGO_PORTABLE", "").strip().lower() in {"1", "true", "yes"}
        if portable:
            return bundle_root()
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / "Binggo"
        return Path.home() / "Binggo"
    return Path(__file__).resolve().parents[1]


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


def _bootstrap_user_data() -> None:
    """首次安装时写入内置活动库与数据源检查点。"""
    from src.activity_store import seed_activities_if_empty
    from src.state_store import seed_state_if_missing

    seed_state_if_missing()
    seed_activities_if_empty()


def ensure_user_dirs() -> None:
    """创建用户目录，并从安装包复制配置模板（仅首次）。"""
    global _SEEDED
    home = user_home()
    data_dir = home / "data"
    config_dir = home / "config"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "output").mkdir(parents=True, exist_ok=True)
    (data_dir / "cache").mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)

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
        _bootstrap_user_data()
    _SEEDED = True


def runtime_label() -> str:
    if is_frozen():
        portable = USER_HOME == bundle_root()
        return "portable" if portable else "installed"
    return "dev"
