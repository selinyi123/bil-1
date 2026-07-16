# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parents[1]

datas = [
    (str(root / "web" / "static"), "web/static"),
    (str(root / "config" / "cookies.txt.example"), "config"),
    (str(root / "config" / "llm.env.example"), "config"),
    (str(root / "config" / "sources.yaml"), "config"),
]

hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette.routing",
    "httpx",
    "qrcode",
    "PIL",
    "PIL.Image",
    "web.app",
    "web.actions",
    "web.activity_service",
    "web.account_service",
    "web.job_runner",
    "web.user_messages",
]

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
    icon=None,
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
