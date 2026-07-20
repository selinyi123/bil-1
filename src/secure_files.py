"""密钥文件尽力权限硬化（C1）：失败只警告，不阻断业务。"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


def harden_file_permissions(path: Path) -> bool:
    """尽力将 path 收紧为仅当前用户可读写。成功 True；跳过/失败 False。"""
    try:
        from src.app_logging import get_logger

        logger = get_logger("secure_files")
    except Exception:
        logger = None  # type: ignore[assignment]

    try:
        target = Path(path)
        if not target.is_file():
            return False
        if sys.platform == "win32":
            if logger is not None:
                logger.debug("跳过 Windows ACL 收紧 path=%s", target)
            return False
        mode = target.stat().st_mode
        new_mode = mode & ~(stat.S_IRWXG | stat.S_IRWXO)
        new_mode |= stat.S_IRUSR | stat.S_IWUSR
        os.chmod(target, new_mode)
        return True
    except Exception as exc:
        if logger is not None:
            logger.warning("无法收紧权限 path=%s: %s", path, exc)
        return False


def write_text_secret(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """原子写密钥文件后尽力 harden。harden 失败不抛。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(target.name + ".tmp")
    try:
        tmp_path.write_text(text, encoding=encoding)
        tmp_path.replace(target)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise
    harden_file_permissions(target)
