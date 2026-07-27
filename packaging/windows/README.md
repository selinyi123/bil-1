# Windows 打包说明

## 小白用户

请前往 GitHub **Releases** 下载：

- `Binggo-Setup-win64.exe` — 推荐，一键安装
- `Binggo-Portable-win64.zip` — 免安装解压即用

安装包**未做商业代码签名**；首次运行若被 SmartScreen 拦截，请选择「仍要运行」。

**覆盖安装前**请先完全退出 Binggo（任务管理器结束所有 `Binggo.exe`，含后台 `--serve` 进程），否则可能提示「拒绝访问」无法替换程序。安装程序会自动尝试结束相关进程。

## 开发者本地构建

需要本机已安装 **Python 3.12+** 与 **Node.js 20+**（`npm`）。安装包 / 便携版用户不需要 Node；Node 仅用于从源码构建前端。可选安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php) 以生成 Setup。

```powershell
cd D:\path\to\bilibili_binggo
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
```

`build.ps1` 会：

1. 从 `src.app_paths.__version__` 读取版本（唯一权威版本号）
2. `python packaging/windows/generate_icon.py`（从 `packaging/assets/app-icon.png` 生成 `binggo.ico`；PNG 由 `scripts/render_brand_png.py` 从 `assets/brand/icon.svg` 导出）
3. `npm ci && npm run build` 构建前端
3. PyInstaller → 便携 ZIP
4. 若本机有 ISCC：以 `/DAppVersion=<version>` 注入 Inno，产出 Setup

跳过安装包：`$env:BINGGO_SKIP_INNO=1`

产物：

- `dist\Binggo\` — 程序目录（含 `Binggo.exe`）
- `dist\Binggo-Portable-win64.zip` — 便携压缩包
- `dist\Binggo-Setup-win64.exe` — 安装包（需 Inno Setup 6）

向导语言：若本机 Inno 含简体中文语言包则可选中文，否则为英文（不影响安装结果）。

## 升级

从 Releases 下载新版 Setup / Portable，自行覆盖安装或解压。概览页「检查更新」仅打开下载页，**不会**自动安装。

## GitHub 自动发布

推送 **Release**（`published`）时，`.github/workflows/release-windows.yml` 会自动构建并上传上述两个文件。

也可在 Actions 页手动 **Run workflow** 下载构建产物（不上传 Release）。

## 环境变量

| 变量 | 说明 |
|------|------|
| `BINGGO_HOME` | 自定义数据目录（覆盖默认 `%APPDATA%\Binggo`） |
| `BINGGO_PORTABLE=1` | 便携模式：数据放在 `Binggo.exe` 同目录 |
| `BINGGO_SKIP_INNO=1` | 本地构建时跳过 Inno |

## 数据目录与安全

| 模式 | 数据根 | 说明 |
|------|--------|------|
| 安装包默认 | `%APPDATA%\Binggo` | 卸载**不删除**此目录 |
| 便携 | exe 同目录 | 含 `config/cookies.txt`、`config/llm.env`；**勿整夹同步到公开盘** |
| 自定义 | `BINGGO_HOME` | 覆盖以上默认 |

密钥仅存本机明文文件；控制台只监听 `127.0.0.1:8181`，请勿改成局域网开放。

## 技术说明

- 启动器：`binggo_launcher.py` → PyInstaller 打包为 `Binggo.exe`
- 界面：本机 `127.0.0.1:8181` + 自动打开浏览器
- 重复双击：若已在运行，会直接打开浏览器而不会启动第二个实例
- 版本 SSOT：`src/app_paths.__version__`（勿在 `installer.iss` 手写正式版本）
