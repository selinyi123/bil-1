# Windows 打包说明

## 小白用户

请前往 GitHub **Releases** 下载：

- `Binggo-Setup-win64.exe` — 推荐，一键安装
- `Binggo-Portable-win64.zip` — 免安装解压即用

## 开发者本地构建

```powershell
cd D:\path\to\bilibili_binggo
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
```

产物：

- `dist\Binggo\` — 程序目录（含 `Binggo.exe`）
- `dist\Binggo-Portable-win64.zip` — 便携压缩包
- `dist\Binggo-Setup-win64.exe` — 安装包（需本机已安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)）

## GitHub 自动发布

推送 **Release**（`published`）时，`.github/workflows/release-windows.yml` 会自动构建并上传上述两个文件。

也可在 Actions 页手动 **Run workflow** 下载构建产物（不上传 Release）。

## 环境变量

| 变量 | 说明 |
|------|------|
| `BINGGO_HOME` | 自定义数据目录（覆盖默认 `%APPDATA%\Binggo`） |
| `BINGGO_PORTABLE=1` | 便携模式：数据放在 `Binggo.exe` 同目录 |

## 技术说明

- 启动器：`binggo_launcher.py` → PyInstaller 打包为 `Binggo.exe`
- 界面：本机 `127.0.0.1:8787` + 自动打开浏览器
- 重复双击：若已在运行，会直接打开浏览器而不会启动第二个实例
