<p align="center">
  <img src="docs/images/logo.svg" alt="Binggo · B站抽奖助手" width="72" height="72">
</p>

<h1 align="center">Binggo</h1>

<p align="center">
  <strong>开源本机 B 站抽奖助手 — 自动发现活动，一键 / 三连参与。</strong><br>
  <em>Open-source local Bilibili lottery helper — discover events and participate from your machine.</em>
</p>

<p align="center">
  <a href="https://github.com/luovicter-collab/bilibinggo/releases/latest">Download</a> ·
  <a href="https://luovicter-collab.github.io/bilibinggo/">Website</a> ·
  <a href="docs/console.md">Documentation</a>
</p>

<p align="center">
  <a href="https://github.com/luovicter-collab/bilibinggo/releases/latest"><img src="https://img.shields.io/github/v/release/luovicter-collab/bilibinggo?style=flat-square" alt="Release"></a>
  <a href="https://github.com/luovicter-collab/bilibinggo/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/luovicter-collab/bilibinggo/ci.yml?branch=main&style=flat-square&label=CI" alt="CI"></a>
  <a href="https://github.com/luovicter-collab/bilibinggo/stargazers"><img src="https://img.shields.io/github/stars/luovicter-collab/bilibinggo?style=flat-square" alt="Stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
</p>

---

## About · 项目简介

**中文：** **Binggo**（亦可作「哔哩哔哩 / B 站抽奖助手」）在本机运行，从多个 UP 合集与监控用户动态增量发现抽奖活动，在网页控制台完成登录、更新、参与与定时调度。Cookie、活动库与参与记录仅保存在你的电脑上；控制台只监听 `127.0.0.1`。官网：[luovicter-collab.github.io/bilibinggo](https://luovicter-collab.github.io/bilibinggo/)。

**English:** Binggo runs locally. It aggregates lottery posts from curated UP collections and watched users, then lets you log in, refresh, and participate (including batch “triple participate”) through a web dashboard. Credentials and data never leave your machine; the server binds to loopback only.

界面动效与防诈说明见 **[官方网站](https://luovicter-collab.github.io/bilibinggo/)**。

---

## Features · 核心能力

| Capability | 中文说明 |
|------------|----------|
| Discovery | UP 合集增量同步 + 监控用户转发动态 |
| Participation | 互动 / 转发 / 预约（关注 + 预约）；充电抽奖自动跳过 |
| Triple participate | 按当前筛选并行参与最多 3 个未参加活动 |
| Scheduler | 内置定时更新与参与；任务撞车时安全停止 |
| Privacy | 登录态与 SQLite 数据目录可配置，默认本机 |
| Cross-platform | Windows 安装包 / 便携版；macOS Apple Silicon |

---

## Quick Start · 快速开始

新安装后活动列表为空是正常的（发行版不内置活动种子）。

| Step | Where | Action |
|------|--------|--------|
| 1 | 侧栏底部 | **扫码登录**（哔哩哔哩 App） |
| 2 | 数据源 → UP 合集 | **更新此源**（日常优先单源；慎用「一键更新」） |
| 3 | 活动 | 筛选「未参加」→ **参与** 或 **三连参与** |

转发抽奖需在概览配置 **LLM API**（互动 / 预约不需要）。补漏可在数据源添加监控用户 MID 并 **更新监控用户动态**。详细说明见 [控制台指南](docs/console.md)。

---

## Download · 下载

| Platform | Artifact | Notes |
|----------|----------|--------|
| Windows | `Binggo-Setup-win64.exe` | 安装包（推荐） |
| Windows | `Binggo-Portable-win64.zip` | 便携版 |
| macOS | `Binggo-macOS-arm64.dmg` | Apple Silicon |
| macOS | `Binggo-macOS-arm64.zip` | 便携 zip |

👉 **[Latest Release](https://github.com/luovicter-collab/bilibinggo/releases/latest)**

| 运行方式 | 控制台地址 |
|----------|------------|
| 安装包 / 便携版 | http://127.0.0.1:8181 |
| 源码开发 | http://127.0.0.1:8787 |

> **Windows：** 未做商业签名；SmartScreen 拦截时选择「仍要运行」。  
> **macOS：** 未做 Apple 公证；首次请右键 → 打开。Intel Mac 请用源码运行。

---

## Documentation · 文档

| Document | Description |
|----------|-------------|
| [docs/console.md](docs/console.md) | 控制台逐页说明 |
| [docs/cli.md](docs/cli.md) | CLI 手册 |
| [docs/quickstart.md](docs/quickstart.md) | 上手补充 |
| [mcp/README.md](mcp/README.md) | 可选 MCP / Skill（不打入安装包） |
| [packaging/windows/README.md](packaging/windows/README.md) | Windows 打包 |
| [packaging/macos/README.md](packaging/macos/README.md) | macOS 打包 |
| [web/frontend/README.md](web/frontend/README.md) | 前端开发 |

---

## Security & Privacy · 安全与隐私

- **Cookie** 保存在本机 `config/cookies.txt`，不会上传。
- **数据目录** 见下表；卸载安装程序不会自动删除用户数据。

| Mode | Data root |
|------|-----------|
| 源码开发 | 仓库根目录 |
| Windows 安装包 | `%APPDATA%\Binggo` |
| Windows 便携 (`BINGGO_PORTABLE=1`) | `Binggo.exe` 同目录 |
| macOS 默认 | `~/Library/Application Support/Binggo` |
| macOS 便携 | `.app` 解压目录 |
| 自定义 | `BINGGO_HOME` |

**谨防诈骗：** 勿轻信私信「你已中奖」并要求转账、预付或交验证码。Binggo 不会私信通知中奖。详见官网 [注意](https://luovicter-collab.github.io/bilibinggo/#notice)。

---

## FAQ

| Question | Answer |
|----------|--------|
| 活动列表为空？ | 登录后对数据源点「更新此源」。 |
| 必须配置 LLM？ | 仅 **转发抽奖** 需要。 |
| 能保证中奖？ | 不能；工具只节省发现与点击时间。 |

---

## Development · 开发

**Requirements:** Python 3.12+, Node.js 20+

```bash
git clone https://github.com/luovicter-collab/bilibinggo.git
cd bilibinggo
pip install -r requirements.txt
cd web/frontend && npm ci && npm run build && cd ../..
python scripts/run_dashboard.py   # http://127.0.0.1:8787
```

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
cd web/frontend && npm ci && npm test && npm run build
```

**品牌图标（维护者）：** 编辑 [`assets/brand/icon.svg`](assets/brand/icon.svg) → `python scripts/sync_brand_icons.py` → `python scripts/render_brand_png.py` → 重新生成 `binggo.ico` / `binggo.icns` → `npm run build`。

| Stack | |
|-------|---|
| SQLite | 活动、参与、任务 |
| SSE | 任务进度；断线回退轮询 |
| Diagnostics | JSONL 日志 + 脱敏导出 |

---

## Changelog · 更新记录

### v5.0.4（2026-07-26）

- 统一品牌图标（暖橙六边形 B）：网页标签、宣传站、侧栏、安装包桌面图标
- README 中英双语重构，移除截图占位
- 宣传站 favicon 使用本地 `favicon.ico` + SVG，修复 Pages 缓存问题

### v5.0.3（2026-07-26）

- DS-7 大锦鲤活动参与支持
- 预约抽奖：关注 + 预约
- LLM「测试连接」修复
- 宣传站上线

### v5.0.2（2026-07-22）

- 修复 Win/macOS 安装包启动（`Asia/Shanghai` 时区）

### v5.0.1 / v5.0.0

见 [Releases](https://github.com/luovicter-collab/bilibinggo/releases)。

---

## Star History

<!-- star-history:start -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/star-history/star-history-dark.svg">
  <img alt="Star history" src="assets/star-history/star-history-light.svg">
</picture>
<!-- star-history:end -->

---

## License

MIT
