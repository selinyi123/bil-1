#!/usr/bin/env bash
# Binggo macOS arm64 鎵撳寘锛氫骇鍑?zip锛堜究鎼猴級+ dmg锛堝畨瑁呯洏锛?
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
  echo "璀﹀憡: 褰撳墠鏋舵瀯涓?$ARCH锛涘畼鏂逛骇鐗╃洰鏍囦负 Apple Silicon (arm64)銆? >&2
fi

echo "==> 璇诲彇鐗堟湰"
APP_VERSION="$(python -c 'from src.app_paths import __version__; print(__version__)')"
echo "    version=$APP_VERSION"

echo "==> 瀹夎渚濊禆"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install 'pyinstaller>=6.0.0' 'pillow>=10.0.0'

echo "==> 鏋勫缓鍓嶇"
if ! command -v npm >/dev/null 2>&1; then
  echo "闇€瑕?Node.js/npm锛堝缓璁?Node 20锛? >&2
  exit 1
fi
(
  cd web/frontend
  npm ci
  npm run build
)
if [[ ! -f web/static/dist/index.html ]]; then
  echo "鍓嶇鏋勫缓澶辫触锛氱己灏?web/static/dist/index.html" >&2
  exit 1
fi

echo "==> 鐢熸垚 icns锛堝彲閫夛級"
python packaging/macos/generate_icns.py || true

echo "==> PyInstaller"
python -m PyInstaller packaging/macos/binggo.spec --noconfirm --clean

APP_PATH="$ROOT/dist/Binggo.app"
if [[ ! -d "$APP_PATH" ]]; then
  if [[ -d "$ROOT/dist/Binggo/Binggo.app" ]]; then
    APP_PATH="$ROOT/dist/Binggo/Binggo.app"
  else
    echo "鏈壘鍒?Binggo.app" >&2
    exit 1
  fi
fi

# ---------- ZIP锛堜究鎼?/ 瑙ｅ帇鍗崇敤锛?---------
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
Binggo macOS锛圓pple Silicon锛?
鐗堟湰锛?APP_VERSION

銆愭帹鑽愩€戜篃鍙笅杞?Binggo-macOS-arm64.dmg锛屾墦寮€鍚庢妸 Binggo 鎷栧埌銆屽簲鐢ㄧ▼搴忋€嶃€?

ZIP 渚挎惡鐢ㄦ硶锛?
1. 瑙ｅ帇鏈?ZIP
2. 棣栨鍚姩锛氬彸閿?Binggo.app 鈫?鎵撳紑锛堝洜鏈叕璇侊紝Gatekeeper 鍙兘鎷︽埅锛?
3. 娴忚鍣ㄤ細鎵撳紑 http://127.0.0.1:8181
4. 鏁版嵁鐩綍锛殈/Library/Application Support/Binggo
5. 渚挎惡妯″紡锛氬弻鍑?BinggoPortable.command锛堟暟鎹啓鍦ㄦ湰瑙ｅ帇鐩綍锛?

闇€瑕?Apple Silicon锛圡1/M2/M3/M4鈥︼級銆侷ntel Mac 璇蜂娇鐢ㄦ簮鐮佽繍琛岋細
  python scripts/run_dashboard.py
EOF

ZIP_PATH="$ROOT/dist/Binggo-macOS-arm64.zip"
rm -f "$ZIP_PATH"
(
  cd "$STAGE"
  zip -ry "$ZIP_PATH" Binggo.app BinggoPortable.command README.txt
)

# ---------- DMG锛堝畨瑁呯洏锛氭嫋鍒板簲鐢ㄧ▼搴忥級----------
echo "==> 鐢熸垚 DMG"
DMG_STAGE="$ROOT/dist/macos-dmg"
DMG_PATH="$ROOT/dist/Binggo-macOS-arm64.dmg"
rm -rf "$DMG_STAGE"
mkdir -p "$DMG_STAGE"
cp -R "$APP_PATH" "$DMG_STAGE/Binggo.app"
ln -s /Applications "$DMG_STAGE/Applications"
cat > "$DMG_STAGE/Read Me.txt" <<EOF
Binggo $APP_VERSION锛圓pple Silicon锛?

瀹夎锛?
1. 灏?Binggo.app 鎷栧埌鍙充晶銆孉pplications銆嶆枃浠跺す
2. 鎵撳紑銆屽惎鍔ㄥ彴銆嶆垨銆屽簲鐢ㄧ▼搴忋€嶉噷鐨?Binggo
3. 棣栨鑻ヨ鎷︽埅锛氬彸閿?Binggo 鈫?鎵撳紑锛堟湭鍋?Apple 鍏瘉锛?
4. 娴忚鍣ㄨ闂?http://127.0.0.1:8181

鏁版嵁鐩綍锛殈/Library/Application Support/Binggo
EOF

rm -f "$DMG_PATH"
# UDZO = 鍘嬬缉鍙鏄犲儚锛涙棤闇€ Developer ID 鍗冲彲鐢熸垚
hdiutil create \
  -volname "Binggo ${APP_VERSION}" \
  -srcfolder "$DMG_STAGE" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "瀹屾垚:"
echo "  鐗堟湰: $APP_VERSION"
echo "  zip: $ZIP_PATH"
echo "  dmg: $DMG_PATH"
