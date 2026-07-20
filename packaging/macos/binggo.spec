# -*- mode: python ; coding: utf-8 -*-
"""macOS PyInstaller spec → Binggo.app（arm64）。"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = Path(SPECPATH).resolve().parents[1]
icon_path = Path(SPECPATH).resolve().parent / "binggo.icns"

# 与 Windows 同等 datas（仅 example / seeds / sources，不含密钥）
datas = [
    (str(root / "web" / "static" / "dist"), "web/static/dist"),
    (str(root / "web" / "static" / "favicon.svg"), "web/static"),
    (str(root / "config" / "cookies.txt.example"), "config"),
    (str(root / "config" / "llm.env.example"), "config"),
    (str(root / "config" / "sources.yaml"), "config"),
    (str(root / "config" / "activities_seed.json"), "config"),
    (str(root / "config" / "state_seed.json"), "config"),
]

hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette.routing",
    "starlette.responses",
    "starlette.staticfiles",
    "httpx",
    "httpcore",
    "anyio",
    "sniffio",
    "h11",
    "httptools",
    "click",
    "qrcode",
    "PIL",
    "PIL.Image",
    "multipart",
    "email_validator",
    "web.app",
    "web.actions",
    "web.activity_service",
    "web.account_service",
    "web.job_runner",
    "web.user_messages",
    "src.dashboard_server",
]
hiddenimports += collect_submodules("src")
hiddenimports += collect_submodules("web")

# 构建时只读版本字符串，避免 import src.app_paths 的副作用
import re

_version_match = re.search(
    r'^__version__\s*=\s*["\']([^"\']+)["\']',
    (root / "src" / "app_paths.py").read_text(encoding="utf-8"),
    re.MULTILINE,
)
APP_VERSION = _version_match.group(1) if _version_match else "0.0.0-dev"

a = Analysis(
    [str(root / "binggo_launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Binggo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Binggo",
)

app = BUNDLE(
    coll,
    name="Binggo.app",
    icon=str(icon_path) if icon_path.exists() else None,
    bundle_identifier="com.bilibinggo.app",
    info_plist={
        "NSHighResolutionCapable": True,
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "CFBundleName": "Binggo",
        "CFBundleDisplayName": "Binggo",
    },
)
