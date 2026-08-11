#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path (Join-Path $Root "binggo_launcher.py"))) {
    $Root = Split-Path $PSScriptRoot -Parent
}
Set-Location $Root

Write-Host "==> 读取版本 (src.app_paths.__version__)"
$AppVersion = (python -c "from src.app_paths import __version__; print(__version__)").Trim()
if (-not $AppVersion) {
    throw "无法读取 src.app_paths.__version__"
}
Write-Host "    version=$AppVersion"

Write-Host "==> 安装打包依赖"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install "pyinstaller>=6.0.0" "pillow>=10.0.0"

Write-Host "==> 构建前端"
Push-Location (Join-Path $Root "web\frontend")
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "需要 Node.js/npm（建议 Node 20）才能从源码构建前端"
}
npm ci
npm run build
Pop-Location
if (-not (Test-Path (Join-Path $Root "web\static\dist\index.html"))) {
    throw "前端构建失败：缺少 web/static/dist/index.html"
}

Write-Host "==> 生成应用图标"
python packaging/windows/generate_icon.py

Write-Host "==> PyInstaller 构建"
python -m PyInstaller packaging/windows/binggo.spec --noconfirm --clean

$DistDir = Join-Path $Root "dist\Binggo"
if (-not (Test-Path (Join-Path $DistDir "Binggo.exe"))) {
    throw "未找到 dist\Binggo\Binggo.exe"
}

Write-Host "==> 生成便携版 ZIP"
$ZipPath = Join-Path $Root "dist\Binggo-Portable-win64.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

$ReadmePortable = @"
Binggo 便携版（Windows）
版本：$AppVersion

1. 解压本 ZIP 到任意文件夹（路径尽量不要有中文）
2. 双击 Binggo.exe
3. 浏览器会自动打开 http://127.0.0.1:8181
4. 按页面提示扫码登录、配置 LLM（转发抽奖需要）

数据默认保存在：%APPDATA%\Binggo
若希望数据放在本文件夹，可创建 BinggoPortable.cmd，内容：
  set BINGGO_PORTABLE=1
  start "" "%~dp0Binggo.exe"

本安装包未做商业代码签名；首次运行若被 SmartScreen 拦截，请选择「仍要运行」。
再次双击 Binggo.exe 可重新打开控制台（若已在运行会直接打开浏览器）。
"@
Set-Content -Path (Join-Path $DistDir "使用说明.txt") -Value $ReadmePortable -Encoding UTF8

Compress-Archive -Path $DistDir -DestinationPath $ZipPath

function Invoke-BinggoInnoSetup {
    param(
        [string]$Version,
        [string]$IsccPath = ""
    )
    if (-not $IsccPath) {
        $candidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
            "D:\WORK\Project Environment\InnoSetup\ISCC.exe"
        )
        $cmdIscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($cmdIscc) { $candidates += $cmdIscc.Source }
        foreach ($c in $candidates) {
            if ($c -and (Test-Path $c)) { $IsccPath = $c; break }
        }
    }
    if (-not $IsccPath -or -not (Test-Path $IsccPath)) {
        Write-Host "跳过安装包：未找到 Inno Setup ISCC.exe"
        return $false
    }
    Write-Host "==> Inno Setup 构建 (AppVersion=$Version)"
    & $IsccPath "/DAppVersion=$Version" (Join-Path $Root "packaging\windows\installer.iss")
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC 失败，退出码 $LASTEXITCODE"
    }
    return $true
}

$SkipInno = $env:BINGGO_SKIP_INNO -eq "1"
if (-not $SkipInno) {
    [void](Invoke-BinggoInnoSetup -Version $AppVersion)
}

Write-Host "完成:"
Write-Host "  版本: $AppVersion"
Write-Host "  程序目录: $DistDir"
Write-Host "  便携 ZIP: $ZipPath"
$SetupPath = Join-Path $Root "dist\Binggo-Setup-win64.exe"
if (Test-Path $SetupPath) {
    Write-Host "  安装包: $SetupPath"
}
