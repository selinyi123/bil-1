#!/usr/bin/env python3
"""macOS arm64 packager: Binggo.app -> zip + dmg."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(cwd or ROOT), check=True)


def main() -> int:
    os.chdir(ROOT)
    py = sys.executable

    arch = subprocess.check_output(["uname", "-m"], text=True).strip()
    if arch != "arm64":
        print(f"WARNING: arch={arch}; official target is Apple Silicon arm64.", file=sys.stderr)

    sys.path.insert(0, str(ROOT))
    from src.app_paths import __version__ as app_version

    print(f"==> version={app_version}")

    print("==> deps")
    run([py, "-m", "pip", "install", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", "-r", "requirements.txt"])
    run([py, "-m", "pip", "install", "pyinstaller>=6.0.0", "pillow>=10.0.0"])

    print("==> frontend")
    if not shutil.which("npm"):
        print("Node.js/npm required (Node 20 recommended)", file=sys.stderr)
        return 1
    run(["npm", "ci"], cwd=ROOT / "web" / "frontend")
    run(["npm", "run", "build"], cwd=ROOT / "web" / "frontend")
    if not (ROOT / "web" / "static" / "dist" / "index.html").is_file():
        print("frontend build failed: missing web/static/dist/index.html", file=sys.stderr)
        return 1

    print("==> icns (optional)")
    subprocess.run([py, str(ROOT / "packaging" / "macos" / "generate_icns.py")], check=False)

    print("==> PyInstaller")
    run([py, "-m", "PyInstaller", "packaging/macos/binggo.spec", "--noconfirm", "--clean"])

    app_path = ROOT / "dist" / "Binggo.app"
    if not app_path.is_dir():
        alt = ROOT / "dist" / "Binggo" / "Binggo.app"
        if alt.is_dir():
            app_path = alt
        else:
            print("Binggo.app not found", file=sys.stderr)
            return 1

    stage = ROOT / "dist" / "macos-stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copytree(app_path, stage / "Binggo.app")

    portable = stage / "BinggoPortable.command"
    portable.write_text(
        "#!/bin/bash\n"
        'cd "$(dirname "$0")"\n'
        "export BINGGO_PORTABLE=1\n"
        'exec "./Binggo.app/Contents/MacOS/Binggo"\n',
        encoding="utf-8",
        newline="\n",
    )
    portable.chmod(0o755)

    (stage / "README.txt").write_text(
        f"Binggo macOS (Apple Silicon)\n"
        f"version: {app_version}\n\n"
        "Recommended: download Binggo-macOS-arm64.dmg and drag Binggo into Applications.\n\n"
        "ZIP portable:\n"
        "1. Unzip\n"
        "2. First launch: right-click Binggo.app -> Open (not notarized)\n"
        "3. Browser: http://127.0.0.1:8181\n"
        "4. Data: ~/Library/Application Support/Binggo\n"
        "5. Portable mode: BinggoPortable.command\n\n"
        "Apple Silicon only (M1+). Intel Mac: python scripts/run_dashboard.py\n",
        encoding="utf-8",
        newline="\n",
    )

    zip_path = ROOT / "dist" / "Binggo-macOS-arm64.zip"
    if zip_path.exists():
        zip_path.unlink()
    run(
        ["zip", "-ry", str(zip_path), "Binggo.app", "BinggoPortable.command", "README.txt"],
        cwd=stage,
    )

    print("==> DMG")
    dmg_stage = ROOT / "dist" / "macos-dmg"
    dmg_path = ROOT / "dist" / "Binggo-macOS-arm64.dmg"
    if dmg_stage.exists():
        shutil.rmtree(dmg_stage)
    dmg_stage.mkdir(parents=True)
    shutil.copytree(app_path, dmg_stage / "Binggo.app")
    applications_link = dmg_stage / "Applications"
    if applications_link.exists() or applications_link.is_symlink():
        applications_link.unlink()
    applications_link.symlink_to("/Applications")
    (dmg_stage / "Read Me.txt").write_text(
        f"Binggo {app_version} (Apple Silicon)\n\n"
        "Install:\n"
        "1. Drag Binggo.app to Applications\n"
        "2. Open Binggo from Applications / Launchpad\n"
        "3. First launch: right-click -> Open (not notarized)\n"
        "4. Browser: http://127.0.0.1:8181\n\n"
        "Data: ~/Library/Application Support/Binggo\n",
        encoding="utf-8",
        newline="\n",
    )
    if dmg_path.exists():
        dmg_path.unlink()
    run(
        [
            "hdiutil",
            "create",
            "-volname",
            f"Binggo {app_version}",
            "-srcfolder",
            str(dmg_stage),
            "-ov",
            "-format",
            "UDZO",
            str(dmg_path),
        ]
    )

    print("done:")
    print(f"  version: {app_version}")
    print(f"  zip: {zip_path}")
    print(f"  dmg: {dmg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
