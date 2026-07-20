# 方向九：分发与安装 — 落地实现规范

> 状态：**已落地** — 编码对照本文；验收以 §18 为准  

> 拍板依据：[09-distribution.md](./09-distribution.md)（**已按建议拍板** + 用户追加 **K1 macOS**）  
> 依赖：方向七诊断包；方向八 `/api/runtime`、数据目录约定；现有 `packaging/windows` + `release-windows.yml`  
> 路线图：[fullstack-roadmap.md](../fullstack-roadmap.md) §9  
> 更新：2026-07-20

本文是编码前的最终规范：版本 SSOT、UI、检查更新、启动器文案、Windows 构建注入、**macOS `.app` 打包与路径**、CI、测试与验收。  

**目标红线：**  
1. 只改 `src/app_paths.__version__`，经构建后 API / UI / 安装包版本一致；  
2. 概览可见 Version，可手动检查更新并打开对应平台下载页；  
3. Windows Setup + Portable **继续可用**；新增 macOS arm64 `.app` zip；  
4. **无**静默强更、**无**商业签名 / Apple 公证、**无**崩溃云上报；业务功能无回归。

---

## 0. 约束摘要（不可违背）

| ID | 约束 |
|----|------|
| **D0** | **不改业务语义**：登录、Job、SSE、调度、LLM、参与文案行为不变 |
| **D1** | 版本 SSOT = `src/app_paths.__version__`（拍板 **A1**）；禁止再手写第二份权威版本号 |
| **D2** | 检查更新 = **用户手动触发**（**B2**）；禁止默认启动强联网、禁止自动下载安装 |
| **D3** | 升级 = 打开 Releases / 下载页，用户自行安装（**E1**） |
| **D4** | 诊断 = 复用方向七/八（**D1**）；禁止新建 crash 表 / 遥测上报 |
| **D5** | Windows：保持 Setup（Inno）+ Portable zip；iss 版本由构建注入 |
| **D6** | macOS：v1 交付 **arm64** `.app` + zip（**K1**）；默认数据目录 `~/Library/Application Support/Binggo` |
| **D7** | 签名：v1 **不做** Authenticode / Developer ID + Notarization（**G1**）；文档说明 SmartScreen / Gatekeeper |
| **D8** | 检查更新仅访问 GitHub API（边角 **①③**）；短超时；失败不阻断控制台 |
| **D9** | 契约代不变；新 API 走统一错误体；优先 `VALIDATION_ERROR` / 既有码 |
| **D10** | 密钥仍不进包：spec 只打 `*.example` + `sources.yaml` + seeds（与现 Windows 一致） |

---

## 1. 拍板对照（实现时勿走样）

| 拍板 | 结论 | 实现落点 |
|------|------|----------|
| A | A1 SSOT | §3 |
| B | B2 手动检查更新 | §5 / §6 |
| C | C1 UI Version | §6 |
| D | D1 复用诊断 | §7 |
| E | E1 用户自装 | §5.4 |
| F | F2 Inno 中文尽力 | §8.3 |
| G | G1 不签名 | §0 D7 / §11.5 / §14 |
| H | H1 + 平台路径 | §4 / §10 |
| I | I1 pytest | §15 |
| J | J1 最小 UI | §6 |
| K | K1 macOS arm64 | §10 / §11 / §12 |
| ①–⑧ | 仓库、semver、超时、文案、分期、Intel、Gatekeeper | 全文对应节 |

---

## 2. 目标目录与文件（编码后应存在）

```text
src/
  app_paths.py              # __version__ SSOT；Darwin frozen 路径；可选 platform_label
  version_info.py           # 新建：解析/比较 semver；读 __version__
  update_check.py           # 新建：GitHub Releases 检查（无 FastAPI）
  dashboard_server.py       # 一般不动（端口策略保持）

binggo_launcher.py          # 失败文案加强；macOS 单实例/对话框；跨平台

web/
  app.py                    # FastAPI version=__version__；注册 updates API
  schemas/updates.py        # 新建：检查更新响应模型

web/frontend/
  index.html                # Version 卡片 + 检查更新按钮
  src/runtime/index.ts      # 展示 version；绑定检查更新

packaging/
  windows/
    build.ps1               # 读 __version__，注入 ISCC /DAppVersion=
    installer.iss           # AppVersion 改为可被 /D 覆盖的默认值
    binggo.spec             # 可不变或注释版本来源
    README.md               # 升级、未签名、版本说明
  macos/                    # 新建
    binggo.spec             # PyInstaller + BUNDLE → Binggo.app
    build.sh                # npm build + pyinstaller + zip
    README.md               # 安装、Gatekeeper、数据目录、Apple Silicon
    generate_icns.py        # 可选：从 png 生成 .icns（或复用 pillow）

.github/workflows/
  release-windows.yml       # 保持；确保用注入后的版本
  release-macos.yml         # 新建：macos-latest arm64 构建并上传 zip
  # 或合并为 release.yml 双 job——实现时二选一，推荐独立文件清晰

tests/
  test_version_info.py
  test_update_check.py
  test_app_paths_macos.py   # Darwin 路径逻辑（可 monkeypatch sys.platform）
  test_updates_api.py
  # 更新 test_runtime_api：断言 version 字段

docs/plans/
  09-distribution.md
  09-distribution-impl.md   # 本文
README.md                   # Windows + macOS 下载与数据目录
```

**禁止：**

- 在 `web/app.py` / `installer.iss` 再手写与 `__version__` 不同的权威版本  
- 启动时默认请求 GitHub（除非用户另拍板 B3）  
- 下载安装包到临时目录并自动执行  
- macOS 强制 Notarization 作为 v1 验收  
- 把 Cookie / llm.env 打进安装包  

---

## 3. 版本单一来源（A1）

### 3.1 权威常量

```python
# src/app_paths.py
__version__ = "4.0.2"  # 发版只改这里（或发版脚本改这里）
```

格式：**严格** `MAJOR.MINOR.PATCH` 三位数字（边角②）。预发布后缀（`-rc.1`）v1 **不支持**进比较逻辑；若需要，落地时比较函数可忽略 `-` 后段，但发版默认不用。

### 3.2 运行时引用

| 位置 | 规范 |
|------|------|
| `web/app.py` | `FastAPI(..., version=__version__)`，`from src.app_paths import __version__` |
| `HealthReport` / diagnostics | 已用 `__version__`，保持 |
| OpenAPI / 关于 API | 不得另写字面量 |

### 3.3 `src/version_info.py`

```python
def get_version() -> str:
    """返回 __version__ 字符串。"""

def parse_version(text: str) -> tuple[int, int, int] | None:
    """去 v/V 前缀；匹配 ^(\d+)\.(\d+)\.(\d+)；失败返回 None。"""

def compare_versions(current: str, latest: str) -> int:
    """current < latest → -1；相等 → 0；current > latest → 1；
    任一方无法 parse → 仅当规范化字符串相等为 0，否则视为「未知」由调用方处理（建议返回 None 或抛 ValueError——推荐返回 Optional[int]，None 表示不可比）。"""
```

**推荐签名（钉死）：**

```python
def compare_versions(current: str, latest: str) -> int | None:
    # None = 不可比（调用方当作「无法判断是否有更新」）
```

### 3.4 Windows 构建注入

`packaging/windows/build.ps1` 在 Inno 之前：

1. 用 Python 打印版本：  
   `python -c "from src.app_paths import __version__; print(__version__)"`  
2. 调用 ISCC：  
   `& $iscc /DAppVersion=$ver packaging/windows/installer.iss`  

`installer.iss`：

```iss
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
```

**禁止**在 iss 再写死 `4.0.2` 作为唯一来源；默认 `0.0.0-dev` 仅防止裸跑 ISCC 时离谱，正式包必须带 `/DAppVersion=`。

`release-windows.yml`：若当前直接 `ISCC installer.iss`，改为调用带注入的脚本步骤（或在 workflow 里读版本再 `/D`）。**与 `build.ps1` 单一路径优先**：workflow 只调 `build.ps1` + 带版本的 ISCC 封装函数。

### 3.5 macOS 构建

`build.sh` 同样读取 `__version__`，写入：

- zip 文件名：`Binggo-macOS-arm64-<version>.zip` **或** 固定 `Binggo-macOS-arm64.zip` 并在 Release body 写版本（**推荐固定名 + Release tag 表达版本**，与 Windows 现命名风格接近：`Binggo-Portable-win64.zip`）  
- 钉死产物名：`dist/Binggo-macOS-arm64.zip`（内含 `Binggo.app`）；版本以 tag / `__version__` 为准  

### 3.6 测试

- `test_version_info.py`：parse / compare / 忽略 `v`  
- 可选：断言 `web.app.app.version == __version__`  

---

## 4. 平台数据目录（H1 + K1）

### 4.1 `user_home()` 改造（权威）

优先级保持：

1. `BINGGO_HOME` 非空 → 该路径  
2. frozen + `BINGGO_PORTABLE` ∈ `{1,true,yes}` → `bundle_root()`  
3. frozen + **非便携**：  
   - **Windows**：`%APPDATA%\Binggo`（现逻辑）  
   - **Darwin**：`~/Library/Application Support/Binggo`  
   - **其它**：`~/Binggo`（兜底）  
4. 非 frozen → 仓库根  

```python
# Darwin 伪代码
support = Path.home() / "Library" / "Application Support" / "Binggo"
```

### 4.2 `bundle_root()` 在 `.app` 内

PyInstaller `.app` 中 `sys.executable` 通常为：  
`Binggo.app/Contents/MacOS/Binggo`  

`bundle_root()` = `Path(sys.executable).resolve().parent` → `.../Contents/MacOS`。  

便携模式数据若放在 MacOS 旁不合理；**便携约定（钉死）：**

- macOS portable：`BINGGO_PORTABLE=1` 时，`user_home()` = **`Binggo.app` 的父目录**（用户解压文件夹），即  
  `Path(sys.executable).resolve().parents[2]`（`MacOS` → `Contents` → `Binggo.app`）的 `.parent`  
  更清晰的辅助函数：

```python
def app_bundle_root() -> Path:
    """返回 Xxx.app 目录；非 .app 结构则退回 executable.parent。"""
```

实现时用路径片段检测 `Contents/MacOS`：若匹配，则 `app_bundle_root = executable.parents[2]`，portable home = `app_bundle_root.parent`。  
非 portable installed：仍用 Application Support。

### 4.3 `runtime_label()`

保持 `dev` / `installed` / `portable`。  
可选增加 `platform` 字段到 `/api/runtime`：`windows` | `macos` | `linux` | `unknown`（便于检查更新文案），**不改变**既有 `runtime` 三值语义。

### 4.4 文档表（README / packaging README 必须一致）

| 模式 | Windows | macOS |
|------|---------|-------|
| 安装/默认 | `%APPDATA%\Binggo` | `~/Library/Application Support/Binggo` |
| 便携 | exe 同目录（`BINGGO_PORTABLE=1`） | `.app` 所在解压目录（`BINGGO_PORTABLE=1`） |
| 覆盖 | `BINGGO_HOME` | 同 |

卸载：Windows Inno 不删 AppData；macOS 无正式 pkg 卸载器时，文档写「删 `.app` 不会自动删 Application Support」。

---

## 5. 检查更新（B2）— `src/update_check.py`

### 5.1 常量

```python
GITHUB_REPO = "luovicter-collab/bilibinggo"  # 边角①
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
USER_AGENT = f"Binggo/{get_version()} (+local-console)"
TIMEOUT_SEC = 8.0
```

### 5.2 核心函数

```python
@dataclass(frozen=True)
class UpdateCheckResult:
    ok: bool
    current: str
    latest: str | None
    update_available: bool
    release_url: str | None
    notes_excerpt: str | None
    message: str  # 人话，成功/失败都可给 UI
    error_kind: str | None  # network | parse | empty | None

def check_for_updates(*, platform: str | None = None) -> UpdateCheckResult:
    ...
```

`platform`：`windows` | `macos` | `None`（自动从 `sys.platform` 推断：`win32`→windows，`darwin`→macos）。

### 5.3 HTTP 行为

- 使用 `httpx`（项目已有）`GET` latest release  
- Headers：`Accept: application/vnd.github+json`，`User-Agent` 如上  
- **不**需要 GitHub token（公开库）；若未来私有再另议  
- 超时 `TIMEOUT_SEC`；任何网络异常 → `ok=False`，`message` 友好，**不抛到 API 500**（API 层可仍 200 + ok false，或 502——**推荐 200 + ok:false**，避免前端当硬错误；若用 AppError 则 `INTERNAL`/`NETWORK` 需有人话。为与方向四一致：**成功体 200 + ok 字段**；校验类才 4xx）

### 5.4 解析

从 JSON 取：

- `tag_name` → `latest`（去 `v`）  
- `html_url` → `release_url`  
- `body` → `notes_excerpt` 截断至 500 字（脱敏：过 `redact_text`）  

`update_available`：`compare_versions(current, latest) == -1`。  
不可比 → `update_available=False`，`message` 说明无法比较。

### 5.5 资源提示（④）

不强制解析 assets 文件名；`message` / 可选字段 `hint`：

| platform | hint 示例 |
|----------|-----------|
| windows | 请下载 Binggo-Setup-win64.exe 或 Binggo-Portable-win64.zip |
| macos | 请下载 Binggo-macOS-arm64.zip（需 Apple Silicon） |

可选：若 `assets[].name` 含 `Setup-win64` / `macOS-arm64`，可填 `download_url` 直链；**有则更好，无则只用 html_url**。

### 5.6 禁止

- 写盘下载  
- 缓存 token  
- 在 Job 线程默认调用  

---

## 6. API 与前端（C1 / J1）

### 6.1 `GET /api/runtime` 扩展

在现有字段上**只增不删**：

```json
{
  "ok": true,
  "version": "4.0.2",
  "runtime": "dev",
  "platform": "windows",
  "user_home": "...",
  "data_dir": "...",
  "config_dir": "...",
  "bind_host": "127.0.0.1",
  "bind_port": 8787,
  "findings": []
}
```

`platform`：由小函数 `platform_label()` → `windows`|`macos`|`linux`|`unknown`。

### 6.2 检查更新 API

```http
POST /api/updates/check
tags: ["stable"]
```

响应模型 `UpdatesCheckOut`：

```json
{
  "ok": true,
  "current": "4.0.2",
  "latest": "4.0.3",
  "update_available": true,
  "release_url": "https://github.com/.../releases/tag/v4.0.3",
  "download_url": null,
  "notes_excerpt": "...",
  "message": "发现新版本 4.0.3",
  "platform": "windows"
}
```

失败（网络等）：仍 HTTP 200，`ok: false`，`message` 说明原因（避免 toast 成「服务器错误」吓人）。  
若坚持 AppError：则 `message` 必须友好——**本文钉死 200+ok 模式**。

### 6.3 前端

**DOM（概览 project-showcase 侧栏）：**

- `#runtime-version` 展示版本  
- `#check-updates` 按钮「检查更新」  
- 可选 `#open-releases` 链到 `https://github.com/luovicter-collab/bilibinggo/releases`  

**逻辑（`runtime/index.ts`）：**

1. `loadRuntimeInfo` 填充 version / runtime / data_dir（已有后两者）  
2. 点击检查更新 → `POST /api/updates/check` → toast：  
   - 有更新：success/info + `window.open(release_url)`（可先 toast 再开，或按钮「前往下载」）  
   - 已最新：success「已是最新」  
   - 失败：error + message  
3. 按钮 loading 态复用 `setButtonLoading`  

**不改** LLM / 登录 / 任务坞。

---

## 7. 启动器与诊断（D1）

### 7.1 `binggo_launcher.py` 失败文案

启动超时时 MessageBox / stderr 必须包含：

1. 日志文件完整路径（`setup_logging` 返回值）  
2. 数据目录（`user_home()` 或 `data_dir()`）  
3. 一句：「若控制台曾能打开，可在概览导出诊断包」  
4. 端口占用提示（保持现有）  

### 7.2 单实例

| 平台 | 策略 |
|------|------|
| Windows | 保持 Mutex `Global\BilibiliBinggoDashboard` |
| macOS / 其它 | **不**用 Win Mutex；依赖现有「端口已占用 → 打开浏览器」逻辑；可选 `fcntl` 文件锁在 `DATA_DIR/.binggo.lock`（**推荐做**，避免双开多个服务进程抢端口前的竞态） |

文件锁规范（若实现）：

- 路径：`data_dir() / ".instance.lock"`  
- 锁失败 → 打开 `DASHBOARD_URL` 并退出 0  
- 锁文件不进诊断包敏感清单（非密钥）  

### 7.3 错误对话框

| 平台 | 实现 |
|------|------|
| Windows | 保持 `MessageBoxW` |
| Darwin | `osascript -e 'display dialog ...'` 或 tkinter；失败则仅 print |
| Linux | print / 可选 zenity（非必须） |

### 7.4 诊断包

可增加一行：`platform: windows|macos`（从 `platform_label()`）。  
仍排除密钥文件。

---

## 8. Windows 打包细节（D5 / F2）

### 8.1 流程（保持）

`npm ci && build` → icon → PyInstaller `binggo.spec` → Portable zip → ISCC（**注入版本**）。

### 8.2 产物名（钉死）

- `dist/Binggo-Setup-win64.exe`  
- `dist/Binggo-Portable-win64.zip`  

### 8.3 Inno 中文（F2）

```iss
[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
```

若 CI 的 Inno 无中文 isl：构建脚本检测文件存在再写入临时 iss，或 catch 后回退仅 english，**不得**让 release 整线失败。  
文档注明向导可能为英文。

### 8.4 便携说明 txt

补充版本号行（构建时写入 `__version__`）；数据目录与方向八一致；未签名说明一句。

---

## 9. Windows CI

`release-windows.yml`：

- 保持 `windows-latest`  
- 确保 ISCC 带 `/DAppVersion=`  
- 上传两文件到 Release  

`ci.yml`（日常 PR）：**不**强制 PyInstaller（太慢）；pytest 覆盖版本/更新逻辑即可。

---

## 10. macOS 路径与启动行为（K1）

### 10.1 目标用户体验

1. 从 Releases 下载 `Binggo-macOS-arm64.zip`  
2. 解压得到 `Binggo.app`  
3. **首次**：右键 → 打开（Gatekeeper，因未公证）  
4. 浏览器打开 `http://127.0.0.1:8181`  
5. 数据在 `~/Library/Application Support/Binggo`  

便携：提供 `BinggoPortable.command`：

```bash
#!/bin/bash
cd "$(dirname "$0")"
export BINGGO_PORTABLE=1
open "./Binggo.app"
```

（或直接执行二进制并带环境变量；`open` 可能不传 env——**更稳妥**：用 `BINGGO_PORTABLE=1 /path/to/Binggo.app/Contents/MacOS/Binggo`。文档与脚本钉死后者。）

### 10.2 架构

- **v1 只构建 `arm64`**（Apple Silicon）  
- README 醒目标注：需要 M1/M2/M3/M4 等；Intel Mac 请源码运行（`python scripts/run_dashboard.py`）或等待后续产物  
- 边角⑦  

### 10.3 控制台窗口

Windows 用 `console=False`。macOS `.app` 同样 **windowed / noconsole**，避免黑终端；日志进文件。

---

## 11. macOS PyInstaller（K1）

### 11.1 目录

`packaging/macos/binggo.spec`：

- Analysis 入口：`binggo_launcher.py`（与 Windows 相同）  
- `datas`：与 Windows 同等列表（dist、favicon、examples、seeds、sources.yaml）  
- `hiddenimports`：与 Windows 对齐（可抽公共 `packaging/common_hiddenimports.py`——**可选**，避免双份漂移；若抽公共，Windows spec 也改 import）  

### 11.2 BUNDLE

```python
app = BUNDLE(
    coll,  # 或 exe
    name="Binggo.app",
    icon="packaging/macos/binggo.icns",  # 若无则暂可不设
    bundle_identifier="com.bilibinggo.app",
    info_plist={
        "NSHighResolutionCapable": True,
        "CFBundleShortVersionString": __version__,  # 构建时写入或 spec 内读
        "CFBundleVersion": __version__,
    },
)
```

onedir + BUNDLE 是 PyInstaller macOS 常规做法；实现时以能双击启动为准，参考 PyInstaller 6.x 文档。

### 11.3 `build.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT=...
cd "$ROOT"
python -m pip install -r requirements.txt 'pyinstaller>=6' pillow
(cd web/frontend && npm ci && npm run build)
# 可选：生成 icns
python -m PyInstaller packaging/macos/binggo.spec --noconfirm --clean
# 打包 zip
ditto -c -k --sequesterRsrc --keepParent dist/Binggo.app dist/Binggo-macOS-arm64.zip
```

在 **arm64** runner 上执行（`macos-latest` 现多为 arm64）。若 runner 为 x86_64，须 `arch -arm64` 或指定 `macos-14`/`macos-15` arm 标签——workflow 里写明 `runs-on: macos-14`（Apple Silicon）。

### 11.4 图标

- 有 `generate_icns.py`：从现有 png/ico 转 icns  
- 无图标也可先发版，验收不强制美工  

### 11.5 签名与 Gatekeeper（G1 / ⑧）

- **不**调用 `notarytool`  
- 可选 `codesign --force --deep --sign - Binggo.app`（ad-hoc），可能改善部分本机体验，**非必须**  
- README：若提示「无法打开，因为无法验证开发者」→ 系统设置或右键打开  

---

## 12. macOS CI（K1）

新建 `.github/workflows/release-macos.yml`：

```yaml
on:
  release:
    types: [published]
  workflow_dispatch:

jobs:
  build-macos:
    runs-on: macos-14   # Apple Silicon
    steps:
      - checkout
      - setup-python 3.12
      - setup-node 20
      - run: bash packaging/macos/build.sh
      - upload artifact / softprops/action-gh-release 上传 Binggo-macOS-arm64.zip
```

与 Windows release **并行**（同一 `published` 事件两个 workflow 均可跑）。  
注意：两个 workflow 同时 `action-gh-release` 上传不同文件一般可行；若冲突，改为单 workflow 双 job。**推荐一个 `release.yml` 含 `build-windows` + `build-macos` job**，共享 `on: release`，避免竞态——实现时优先合并，文件名可仍拆 README 说明。

**本文钉死推荐：** 扩展为 `.github/workflows/release.yml`（或保留 windows 文件并新增 macos，用 `needs` 无强制）。验收：一次 Release 能挂上 Win 双文件 + Mac zip。

---

## 13. 检查更新与多平台文案

`check_for_updates` 根据 platform 设置 `message`/`hint`：

- 当前已是最新：不分平台  
- 有更新：附带对应产物文件名提示  
- UI 不自动选 assets；打开 `release_url` 即可  

---

## 14. 文档（必须改）

### 14.1 根 `README.md`

- 下载区：Windows Setup / Portable + **macOS arm64**  
- 数据目录表含 macOS Application Support  
- Gatekeeper / 未签名说明  
- 版本以程序内关于区为准  

### 14.2 `packaging/windows/README.md`

- `/DAppVersion` 注入说明  
- 升级步骤  

### 14.3 `packaging/macos/README.md`（新建）

- 构建依赖（Python 3.12、Node 20、Apple Silicon Mac 或 CI）  
- 用户安装步骤与 Gatekeeper  
- 便携模式  
- 明确 **不支持** Intel 官方包（v1）  

---

## 15. 测试矩阵（I1）

| 测试 | 覆盖 |
|------|------|
| `test_version_info.py` | parse、compare、`v` 前缀、不可比 |
| `test_update_check.py` | mock httpx：有更新/已最新/网络失败/坏 JSON |
| `test_updates_api.py` | POST `/api/updates/check` 形状；mock 下层 |
| `test_runtime_api.py` | `version`、`platform` 存在 |
| `test_app_paths` 扩展 | monkeypatch `sys.platform`+`is_frozen` 断言 Darwin Application Support；portable `.app` 结构 |
| 前端 | 不强制 E2E；手动点检查更新即可 |

**不在** PR 的 `ci.yml` 跑 PyInstaller mac/win（耗时/贵）；release workflow 负责产物。

---

## 16. 分期（⑥ + K）

| 期 | 内容 | 退出标准 |
|----|------|----------|
| **P1** | SSOT：`__version__` 引用；Windows 构建注入；UI 显示 Version；`platform` 字段；路径 Darwin 分支（即使尚未出包） | 单测绿；手改版本后 API/UI 一致 |
| **P2** | `update_check` + API + 按钮；hint 分平台 | mock 测通；手测有/无网 |
| **P3** | 启动器文案 + 可选文件锁；Inno 中文尽力；文档未签名 | 启动失败文案含日志路径 |
| **P4** | `packaging/macos` + `build.sh` + release CI 上传 zip；macos README | CI 产出可下载 zip；真机或文档验收 Gatekeeper 步骤 |

允许 P1+P2 同 PR；P4 可独立 PR，但路径逻辑应在 P1 先合入以免 mac 包数据写到错误目录。

---

## 17. 实现顺序建议

1. `version_info.py` + `__version__` 全引用 + Windows `/DAppVersion`  
2. `user_home()` Darwin + `platform_label()` + runtime API  
3. 前端 Version 展示  
4. `update_check.py` + API + 按钮  
5. 启动器文案 / 锁  
6. macOS spec + build.sh + CI  
7. 文档三处对齐  

---

## 18. 验收红线

- [ ] 只改 `app_paths.__version__` + 走官方构建后，Windows Setup 版本、API `version`、UI Version 一致  
- [ ] 概览显示 Version；检查更新：最新 / 有新版 / 无网 三种表现正确  
- [ ] Windows Release 仍产出 Setup + Portable  
- [ ] macOS Release 产出 `Binggo-macOS-arm64.zip`（含 `.app`）  
- [ ] frozen Darwin 默认数据目录为 Application Support；便携约定符合 §4.2  
- [ ] **无**自动安装、**无**公证强制、**无**崩溃上报  
- [ ] 业务 pytest 全绿；新增单测通过  
- [ ] README 含 macOS 安装与 Gatekeeper 说明  

---

## 19. 非目标（再次钉死）

- Mac App Store / 微软商店  
- Apple Notarization / 商业 EV 签名（可另立「方向九补遗」）  
- Intel Mac 官方包、Linux AppImage（另议）  
- 静默强更、差分补丁  
- 用更新通道替换 GitHub Releases  
- 方向十 MCP  

---

## 20. 编码中禁止的「聪明优化」

| 冲动 | 为何禁止 |
|------|----------|
| 启动自动检查更新 | 违背 B2 |
| 下载 exe/dmg 自动跑 | 违背 E1 / 安全 |
| mac 数据仍用 `~/Binggo` 凑合 | 不符合平台惯例，难找数据 |
| portable 数据写进 `Contents/MacOS` | 升级/签名/权限混乱 |
| 为公证申请证书阻塞发版 | 违背 G1 与用户「先能跑」 |
| 在 pytest CI 打完整 mac/win 包 | 成本高，留给 release |

---

## 21. 状态与检查清单

| 项 | 状态 |
|----|------|
| 拍板 A–K / 边角 | ✅ |
| 本文落地规范 | ✅ 成文 |
| P1–P4 编码 | ✅ |
| 验收 §18 | ⏳ 以 pytest + 手测 / Release 产物为准 |

### 合并前自检

- [x] §0 约束未破  
- [x] 无第二份权威版本号  
- [x] 检查更新手动、短超时、200+ok 失败模式  
- [x] Darwin 路径与便携约定正确  
- [x] Release 能挂 Win + Mac 产物（workflow 已就绪）  
- [x] 文档 Gatekeeper / Apple Silicon 写清  

讨论记录：

| 日期 | 内容 |
|------|------|
| 2026-07-20 | 按建议拍板；用户追加 macOS；本文成文待编码 |
| 2026-07-20 | P1–P4 编码落地（SSOT / 检查更新 / 启动器 / Win+Mac 打包 CI） |
