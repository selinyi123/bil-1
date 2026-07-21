# Binggo

**本机 B 站抽奖助手** — 从 UP 合集与监控用户动态里发现活动，在网页控制台一键参与、追踪状态。

Cookie、LLM 密钥与活动库全部保存在你的电脑上；控制台只监听 `127.0.0.1`，**不会上传到任何服务器**。

[![Release](https://img.shields.io/github/v/release/luovicter-collab/bilibinggo?style=flat-square)](https://github.com/luovicter-collab/bilibinggo/releases/latest)
[![CI](https://img.shields.io/github/actions/workflow/status/luovicter-collab/bilibinggo/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/luovicter-collab/bilibinggo/actions/workflows/ci.yml)
[![Stars](https://img.shields.io/github/stars/luovicter-collab/bilibinggo?style=flat-square)](https://github.com/luovicter-collab/bilibinggo/stargazers)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)

<p align="center">
  <img src="assets/screenshots/overview.png" alt="Binggo 概览页：账号状态、活动统计与快捷操作" width="900">
</p>
<p align="center">
  <img src="assets/screenshots/activities.png" alt="Binggo 活动页：筛选、三连参与与活动列表" width="900">
</p>

---

## 为什么用它

| | |
|---|---|
| **完全本机** | 登录态与数据不出电脑；适合在意隐私的日常使用 |
| **双通道发现** | 内置抽奖合集 + 监控用户转发，少漏活动 |
| **一键参与** | 互动 / 转发 / 预约；支持「三连参与」并行冲前几条 |
| **开箱可装** | Windows Setup / 便携包 + macOS Apple Silicon DMG |

---

## 安装

从 [Releases](https://github.com/luovicter-collab/bilibinggo/releases/latest) 下载：

| 包 | 说明 |
|----|------|
| `Binggo-Setup-win64.exe` | Windows 安装包（推荐） |
| `Binggo-Portable-win64.zip` | Windows 便携版 |
| `Binggo-macOS-arm64.dmg` | macOS Apple Silicon（推荐：拖到「应用程序」） |
| `Binggo-macOS-arm64.zip` | macOS 便携 zip |

启动后打开控制台：

| 运行方式 | 地址 |
|----------|------|
| **安装包** | http://127.0.0.1:8181 |
| **源码**（见下） | http://127.0.0.1:8787 |

> **Windows：** 未做商业签名；若 SmartScreen 拦截，选择「仍要运行」。  
> **macOS：** 未做 Apple 公证；首次请右键 → 打开。Intel Mac 请用下方源码方式运行。

### 从源码运行

需要 **Python 3.12+** 与 **Node.js 20+**（构建前端）。

```bash
git clone https://github.com/luovicter-collab/bilibinggo.git
cd bilibinggo
pip install -r requirements.txt
cd web/frontend && npm ci && npm run build && cd ../..
python scripts/run_dashboard.py   # http://127.0.0.1:8787
```

---

## 五分钟上手

发行版**不预填**活动或检查点，首次打开活动列表为空，属于正常情况。

| 步骤 | 在哪里 | 做什么 |
|------|--------|--------|
| 1 | 侧栏底部 | **扫码登录**（哔哩哔哩 App） |
| 2 | 概览 → LLM 配置 | 填 API Key / 模型 → **测试连接** → **保存**（玩转发抽奖时需要） |
| 3 | 数据源 → UP 合集 | 对需要的合集点 **「更新此源」**（优先单源；少用「一键更新」） |
| 4 | 活动 | 筛选未参加 → 单条参与，或顶部 **「三连参与」** |

可选：在数据源添加常转发抽奖的用户 MID，再点 **「更新监控用户动态」**，补合集漏抓的活动。

运行中任务看右下角 **任务日志**；顶部会出现进度条与结果摘要。

更细的页面说明见 [控制台指南](docs/console.md)。

---

## 功能一览

| 能力 | 说明 |
|------|------|
| 双通道发现 | 多个 UP 合集 + 监控用户转发动态 |
| 一键参与 | 互动 / 转发 / 预约；充电抽奖自动跳过；支持三连 |
| 本地 SQLite | 活动、参与、检查点与任务落在本机数据库 |
| 实时进度 | SSE 推送任务进度与日志；断线回退轮询 |
| 定时点击 | 控制台内调度器；撞车即停，不取消正在跑的抽奖任务 |
| 参与文案 | 自定义或随机借用评论（不足时用兜底） |
| 结构化日志 | JSONL + 概览「导出诊断包」（脱敏，无 Cookie / API Key） |
| 检查更新 | 概览手动检查 GitHub Releases（不自动下载安装） |
| 跨平台分发 | Windows Setup / Portable + macOS arm64 |

设计与演进见 [docs/fullstack-roadmap.md](docs/fullstack-roadmap.md)。  
可选本地 [MCP / Skill](mcp/README.md) 扩展（不打入安装包）。

---

## 数据与隐私

| 模式 | 数据根目录 |
|------|------------|
| 源码开发 | 仓库根目录 |
| Windows 安装包 | `%APPDATA%\Binggo` |
| Windows 便携（`BINGGO_PORTABLE=1`） | `Binggo.exe` 同目录 |
| macOS 默认 | `~/Library/Application Support/Binggo` |
| macOS 便携（`BINGGO_PORTABLE=1`） | `.app` 所在解压目录 |
| 自定义 | `BINGGO_HOME` |

常见文件：`data/binggo.db`、`data/logs/binggo.log`、`config/cookies.txt`、`config/llm.env`、`config/sources.yaml`。

卸载 Windows 程序或删除 `.app` **不会**自动删除数据目录。凭证已在 `.gitignore` 中，请勿提交。

---

## 开发

```bash
# 后端测试
pip install -r requirements-dev.txt
python -m pytest tests/ -q

# 前端
cd web/frontend
npm ci
npm test
npm run build

# E2E（隔离数据目录，端口 8791）
npx playwright install chromium
npm run test:e2e
```

| 文档 | 说明 |
|------|------|
| [docs/console.md](docs/console.md) | 控制台逐页说明 |
| [docs/fullstack-roadmap.md](docs/fullstack-roadmap.md) | 全栈方向总览 |
| [docs/cli.md](docs/cli.md) | CLI 手册 |
| [packaging/windows/README.md](packaging/windows/README.md) | Windows 打包 |
| [packaging/macos/README.md](packaging/macos/README.md) | macOS 打包与 Gatekeeper |
| [web/frontend/README.md](web/frontend/README.md) | 前端开发 |
| [mcp/README.md](mcp/README.md) | 本地 MCP 扩展 |

可选：本地调试用种子导出（**不随发行版分发**）：

```bash
python scripts/export_activities_seed.py
python scripts/export_state_seed.py
```

旧 JSON 活动库迁入 SQLite：`python scripts/import_json_to_db.py`

---

## 更新记录

### v5.0.1（2026-07-21）

- 修复转发抽奖开奖时间：按北京日历串解析 `lottery_time`
- 发行包仍**不**内置活动库 / 数据源 state 种子（新安装需自行「更新此源」）
- 可选本地 MCP / Skill 随源码提供，不打入安装包

### v5.0.0（2026-07-20）

- **Breaking：** 发行版不再内置活动库与 state 种子；首次活动列表为空属正常
- 全栈能力合集：SQLite、任务模型、SSE、检查更新、Win + macOS 安装包

更早版本见 [Releases](https://github.com/luovicter-collab/bilibinggo/releases)。

---

## Star History

仓库内自托管图表（由 Actions 自动更新），不依赖 star-history.com：

<!-- star-history:start -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/star-history/star-history-dark.svg">
  <img alt="Star history" src="assets/star-history/star-history-light.svg">
</picture>
<!-- star-history:end -->

---

## License

MIT
