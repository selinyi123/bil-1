#!/usr/bin/env bash
# Binggo macOS arm64 打包：产出 dist/Binggo-macOS-arm64.zip
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
  echo "警告: 当前架构为 $ARCH；官方产物目标为 Apple Silicon (arm64)。" >&2
fi

echo "==> 读取版本"
APP_VERSION="$(python -c 'from src.app_paths import __version__; print(__version__)')"
echo "    version=$APP_VERSION"

echo "==> 安装依赖"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install 'pyinstaller>=6.0.0' 'pillow>=10.0.0'

echo "==> 构建前端"
if ! command -v npm >/dev/null 2>&1; then
  echo "需要 Node.js/npm（建议 Node 20）" >&2
  exit 1
fi
(
  cd web/frontend
  npm ci
  npm run build
)
if [[ ! -f web/static/dist/index.html ]]; then
  echo "前端构建失败：缺少 web/static/dist/index.html" >&2
  exit 1
fi

echo "==> 生成 icns（可选）"
python packaging/macos/generate_icns.py || true

echo "==> PyInstaller"
python -m PyInstaller packaging/macos/binggo.spec --noconfirm --clean

APP_PATH="$ROOT/dist/Binggo.app"
if [[ ! -d "$APP_PATH" ]]; then
  # 部分 PyInstaller 版本把 .app 放在 dist/Binggo/Binggo.app
  if [[ -d "$ROOT/dist/Binggo/Binggo.app" ]]; then
    APP_PATH="$ROOT/dist/Binggo/Binggo.app"
  else
    echo "未找到 Binggo.app" >&2
    exit 1
  fi
fi

# 便携启动脚本（放在 zip 同级，与 .app 一起）
STAGE="$ROOT/dist/macos-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP_PATH" "$STAGE/Binggo.app"
cat > "$STAGE/BinggoPortable.command" <<'EOF'
#!/bin/bash
cd "$(dirname "$0")"
export BINGGO_PORTABLE=1
exec "./Binggo.app/Contents/MacOS/Binggo"
EOF
chmod +x "$STAGE/BinggoPortable.command"

cat > "$STAGE/README.txt" <<EOF
Binggo macOS（Apple Silicon）
版本：$APP_VERSION

1. 解压本 ZIP
2. 首次启动：右键 Binggo.app → 打开（因未公证，Gatekeeper 可能拦截）
3. 浏览器会打开 http://127.0.0.1:8181
4. 数据目录：~/Library/Application Support/Binggo
5. 便携模式：双击 BinggoPortable.command（数据写在本解压目录）

需要 Apple Silicon（M1/M2/M3/M4…）。Intel Mac 请使用源码运行：
  python scripts/run_dashboard.py
EOF

ZIP_PATH="$ROOT/dist/Binggo-macOS-arm64.zip"
rm -f "$ZIP_PATH"
(
  cd "$STAGE"
  zip -ry "$ZIP_PATH" Binggo.app BinggoPortable.command README.txt
)

echo "完成:"
echo "  版本: $APP_VERSION"
echo "  zip: $ZIP_PATH"
