# macOS 打包说明（Apple Silicon / arm64）

## 用户安装

请前往 GitHub **Releases** 下载（二选一）：

| 文件 | 说明 |
|------|------|
| **`Binggo-macOS-arm64.dmg`（推荐）** | 打开后把 `Binggo.app` 拖到「应用程序」 |
| `Binggo-macOS-arm64.zip` | 解压即用；含便携启动脚本 |

### 使用 DMG（推荐）

1. 打开 `Binggo-macOS-arm64.dmg`
2. 将 **Binggo** 拖到右侧 **Applications**
3. **首次**：在「应用程序」里右键 Binggo → **打开**（因未做 Apple 公证）
4. 浏览器打开 **http://127.0.0.1:8181**
5. 数据目录：`~/Library/Application Support/Binggo`

### 使用 ZIP

1. 解压得到 `Binggo.app`
2. **首次**：右键 → **打开**
3. 其余同上

**需要 Apple Silicon（M1/M2/M3/M4…）。** Intel Mac 请使用源码：`python scripts/run_dashboard.py`。

删除 `.app` **不会**自动删除 Application Support 里的数据。

### 便携模式（ZIP）

解压包内 `BinggoPortable.command`：

```bash
export BINGGO_PORTABLE=1
./Binggo.app/Contents/MacOS/Binggo
```

数据写在 `.app` 所在解压目录（勿写进 `Contents/MacOS`）。

### 未签名说明

v1 不做 Developer ID + Notarization。若提示「无法验证开发者」：系统设置 → 隐私与安全性 → 仍要打开，或始终用右键打开。

> 说明：macOS 常见分发是 **DMG**（拖到应用程序），不是 Windows 那种 Setup.exe 向导；效果等价于「安装到应用程序文件夹」。正式 `.pkg` 安装器在未签名时体验往往更差，故 v1 以 DMG 为准。

---

## 开发者本地构建

需要 **Apple Silicon Mac**（或 CI `macos-14`）、Python 3.12+、Node 20+：

```bash
bash packaging/macos/build.sh
```

产物：

- `dist/Binggo-macOS-arm64.dmg` — 安装盘
- `dist/Binggo-macOS-arm64.zip` — 便携包（含 `Binggo.app`、便携脚本与说明）

版本号来自 `src/app_paths.__version__`（写入 Info.plist）。

## GitHub 自动发布

推送 Release 时，`.github/workflows/release-macos.yml` 在 `macos-14` 上构建并上传 **dmg + zip**。

也可在 Actions 页手动 **Run workflow**，再把产物挂到指定 Release。

## 环境变量

| 变量 | 说明 |
|------|------|
| `BINGGO_HOME` | 自定义数据目录 |
| `BINGGO_PORTABLE=1` | 便携：数据在 `.app` 父目录 |

## 技术说明

- 入口：`binggo_launcher.py` → PyInstaller → `Binggo.app`
- DMG：`hdiutil` 打包（含 Applications 符号链接）
- 控制台：`127.0.0.1:8181`，无终端窗口（日志进文件）
- 密钥不打进包（仅 `*.example` + seeds + `sources.yaml`）
