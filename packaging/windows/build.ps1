#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path (Join-Path $Root "binggo_launcher.py"))) {
    $Root = Split-Path $PSScriptRoot -Parent
}
Set-Location $Root

Write-Host "==> 安装打包依赖"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller>=6.0.0

Write-Host "==> PyInstaller 构建"
python -m PyInstaller packaging/windows/binggo.spec --noconfirm --clean

$DistDir = Join-Path $Root "dist\Binggo"
if (-not (Test-Path (Join-Path $DistDir "Binggo.exe"))) {
    throw "未找到 dist\Binggo\Binggo.exe"
}

Write-Host "==> 生成便携版 ZIP"
$ZipPath = Join-Path $Root "dist\Binggo-Portable-win64.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path $DistDir -DestinationPath $ZipPath

$ReadmePortable = @"
Binggo 便携版（Windows）

1. 解压本 ZIP 到任意文件夹（路径尽量不要有中文）
2. 双击 Binggo.exe
3. 浏览器会自动打开 http://127.0.0.1:8787
4. 按页面提示扫码登录、配置 LLM（转发抽奖需要）

数据默认保存在：%APPDATA%\Binggo
若希望数据放在本文件夹，可创建 BinggoPortable.cmd，内容：
  set BINGGO_PORTABLE=1
  start "" "%~dp0Binggo.exe"

再次双击 Binggo.exe 可重新打开控制台（若已在运行会直接打开浏览器）。
"@
Set-Content -Path (Join-Path $DistDir "使用说明.txt") -Value $ReadmePortable -Encoding UTF8

Write-Host "完成:"
Write-Host "  程序目录: $DistDir"
Write-Host "  便携 ZIP: $ZipPath"
