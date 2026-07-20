#!/usr/bin/env bash
# Binggo macOS arm64: zip (portable) + dmg (install disk)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
  echo "WARNING: arch=$ARCH; official target is Apple Silicon arm64." >&2
fi

echo "==> version"
APP_VERSION="$("$PYTHON" -c 'from src.app_paths import __version__; print(__version__)')"
echo "    version=$APP_VERSION"

echo "==> deps"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r requirements.txt
"$PYTHON" -m pip install 'pyinstaller>=6.0.0' 'pillow>=10.0.0'

echo "==> frontend"
if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js/npm required (Node 20 recommended)" >&2
  exit 1
fi
(
  cd web/frontend
  npm ci
  npm run build
)
if [[ ! -f web/static/dist/index.html ]]; then
  echo "frontend build failed: missing web/static/dist/index.html" >&2
  exit 1
fi

echo "==> icns (optional)"
"$PYTHON" packaging/macos/generate_icns.py || true

echo "==> PyInstaller"
"$PYTHON" -m PyInstaller packaging/macos/binggo.spec --noconfirm --clean

APP_PATH="$ROOT/dist/Binggo.app"
if [[ ! -d "$APP_PATH" ]]; then
  if [[ -d "$ROOT/dist/Binggo/Binggo.app" ]]; then
    APP_PATH="$ROOT/dist/Binggo/Binggo.app"
  else
    echo "Binggo.app not found" >&2
    exit 1
  fi
fi

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
Binggo macOS (Apple Silicon)
version: $APP_VERSION

Recommended: download Binggo-macOS-arm64.dmg and drag Binggo into Applications.

ZIP portable:
1. Unzip
2. First launch: right-click Binggo.app -> Open (not notarized)
3. Browser: http://127.0.0.1:8181
4. Data: ~/Library/Application Support/Binggo
5. Portable mode: BinggoPortable.command

Apple Silicon only (M1+). Intel Mac: python scripts/run_dashboard.py
EOF

ZIP_PATH="$ROOT/dist/Binggo-macOS-arm64.zip"
rm -f "$ZIP_PATH"
(
  cd "$STAGE"
  zip -ry "$ZIP_PATH" Binggo.app BinggoPortable.command README.txt
)

echo "==> DMG"
DMG_STAGE="$ROOT/dist/macos-dmg"
DMG_PATH="$ROOT/dist/Binggo-macOS-arm64.dmg"
rm -rf "$DMG_STAGE"
mkdir -p "$DMG_STAGE"
cp -R "$APP_PATH" "$DMG_STAGE/Binggo.app"
ln -s /Applications "$DMG_STAGE/Applications"
cat > "$DMG_STAGE/Read Me.txt" <<EOF
Binggo $APP_VERSION (Apple Silicon)

Install:
1. Drag Binggo.app to Applications
2. Open Binggo from Applications / Launchpad
3. First launch: right-click -> Open (not notarized)
4. Browser: http://127.0.0.1:8181

Data: ~/Library/Application Support/Binggo
EOF

rm -f "$DMG_PATH"
hdiutil create \
  -volname "Binggo ${APP_VERSION}" \
  -srcfolder "$DMG_STAGE" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "done:"
echo "  version: $APP_VERSION"
echo "  zip: $ZIP_PATH"
echo "  dmg: $DMG_PATH"
