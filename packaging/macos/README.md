# macOS 打包说明（Apple Silicon / arm64）

## 用户安装

请前往 GitHub **Releases** 下载 `Binggo-macOS-arm64.zip`：

1. 解压得到 `Binggo.app`
2. **首次**：右键 → **打开**（因未做 Apple 公证，Gatekeeper 可能拦截双击）
3. 浏览器打开 **http://127.0.0.1:8181**
4. 数据目录：`~/Library/Application Support/Binggo`

**需要 Apple Silicon（M1/M2/M3/M4…）。** Intel Mac 请使用源码：`python scripts/run_dashboard.py`。

删除 `.app` **不会**自动删除 Application Support 里的数据。

### 便携模式

解压包内 `BinggoPortable.command`：

```bash
export BINGGO_PORTABLE=1
./Binggo.app/Contents/MacOS/Binggo
```

数据写在 `.app` 所在解压目录（勿写进 `Contents/MacOS`）。

### 未签名说明

v1 不做 Developer ID + Notarization。若提示「无法验证开发者」：系统设置 → 隐私与安全性 → 仍要打开，或始终用右键打开。

---

## 开发者本地构建

需要 **Apple Silicon Mac**（或 CI `macos-14`）、Python 3.12+、Node 20+：

```bash
bash packaging/macos/build.sh
```

产物：`dist/Binggo-macOS-arm64.zip`（内含 `Binggo.app`、便携脚本与说明）。

版本号来自 `src/app_paths.__version__`（写入 Info.plist）。

## GitHub 自动发布

推送 Release 时，`.github/workflows/release-macos.yml` 在 `macos-14` 上构建并上传 zip。

## 环境变量

| 变量 | 说明 |
|------|------|
| `BINGGO_HOME` | 自定义数据目录 |
| `BINGGO_PORTABLE=1` | 便携：数据在 `.app` 父目录 |

## 技术说明

- 入口：`binggo_launcher.py` → PyInstaller → `Binggo.app`
- 控制台：`127.0.0.1:8181`，无终端窗口（日志进文件）
- 密钥不打进包（仅 `*.example` + seeds + `sources.yaml`）
