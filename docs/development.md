# 开发环境与历史踩坑（Development）

> 本机开发环境说明与历史踩坑记录，是操作参考，不是验收标准。
> 产品安全不变量见 ACCEPTANCE.md；审计状态见 docs/14；系统规格见 SPEC.md。

## 本机开发环境（示例，非仓库规范）

以下为当前开发机实测路径与版本；CI、协作者或其他机器按各自环境配置，不要求一致。

| 工具 | 本机路径/版本 |
|---|---|
| Python | 3.12（当前验证 3.12.10）：C:\Users\Administrator\AppData\Local\Programs\Python\Python312 |
| Node.js/npm | Node 20+（以 web/frontend/package-lock.json 为准）：D:\WORK\Project Environment\NodeJS |
| PyInstaller | 当前命令版本 6.22.0（以 spec 与构建脚本为准）：Python 环境 Scripts\pyinstaller.exe |
| Inno Setup | ISCC 6（不得在 installer.iss 手写版本）：D:\WORK\Project Environment\InnoSetup\ISCC.exe |
| code-review-graph | 仅仓库已有 .code-review-graph 且工具可用时运行：D:\WORK\Project Environment\code-review-graph |

最小环境验证：

    python --version
    python -m pip check
    $env:PATH = "D:\WORK\Project Environment\NodeJS;$env:PATH"
    node --version
    npm --version

注意：D:\TOOL 下的 Binggo 安装目录是兼容/运行入口，不是开发工具的规范安装根；共享工具优先使用 D:\WORK\Project Environment。

## 历史踩坑（Troubleshooting）

- ORM：`session_scope` 块外访问 row 属性会 DetachedInstanceError（曾致 clear_follows 台账静默空集）——读取必须在块内。
- PowerShell 转义：`git rev-parse 'hash^{tree}'` 需单引号；python 内联字符串注意引号。
- GitHub 直连可能间歇性被阻断：`gh api` 可重建推送（内容一致，commit sha 因日期归一化不同）。
- 测试隔离：新模块引用静态 `DATA_DIR` 时须确认 `isolated_home` fixture 已覆盖（conftest 模块列表）。
- 前端构建产物 `web/static/dist` 被 gitignore，改前端源码后需本地 build 才生效。
- Node 不在 PATH 时：`$env:PATH = "D:\WORK\Project Environment\NodeJS;...;$env:PATH"`。
