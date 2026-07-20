# Binggo

本地 B 站抽奖助手：从多个 UP 合集与监控用户动态里发现活动，在本机网页控制台一键参与、追踪状态。

[![Release](https://img.shields.io/github/v/release/luovicter-collab/bilibinggo?style=flat-square)](https://github.com/luovicter-collab/bilibinggo/releases/latest)
[![CI](https://img.shields.io/github/actions/workflow/status/luovicter-collab/bilibinggo/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/luovicter-collab/bilibinggo/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)

控制台只监听本机 `127.0.0.1`。Cookie、LLM 密钥与活动库全部保存在你的电脑上，不会上传到任何服务器。

---

## Install

从 [Releases](https://github.com/luovicter-collab/bilibinggo/releases/latest) 下载：

| 包 | 说明 |
|----|------|
| `Binggo-Setup-win64.exe` | Windows 安装包（推荐） |
| `Binggo-Portable-win64.zip` | Windows 便携版 |
| `Binggo-macOS-arm64.dmg` | macOS Apple Silicon（推荐：拖到「应用程序」） |
| `Binggo-macOS-arm64.zip` | macOS 便携 zip |

启动后打开 **http://127.0.0.1:8181**。

> **Windows：** 未做商业签名；若 SmartScreen 拦截，选择「仍要运行」。  
> **macOS：** 未做 Apple 公证；首次请右键 → 打开。Intel Mac 请用下方源码方式运行。

### From source

需要 **Python 3.12+** 与 **Node.js 20+**（构建前端）。

```bash
git clone https://github.com/luovicter-collab/bilibinggo.git
cd bilibinggo
pip install -r requirements.txt
cd web/frontend && npm ci && npm run build && cd ../..
python scripts/run_dashboard.py   # http://127.0.0.1:8787
```

---

## Quick start

安装包**不再预填**活动或数据源检查点。首次使用请按下面顺序：

1. **扫码登录**（侧栏底部）
2. 若要玩转发抽奖：在概览配置 **LLM**，先「测试连接」再「保存」
3. 打开 **数据源**，对需要的 UP 合集点 **「更新此源」**（推荐；少用「一键更新」以免风控）
4. 到 **活动** 页筛选并参与，或使用「三连参与」

可选：添加监控用户 MID，用「更新监控用户动态」补充合集漏抓的活动。

---

## Features

| 能力 | 说明 |
|------|------|
| 双通道发现 | 6 个 UP 合集 + 监控用户转发动态 |
| 一键参与 | 互动 / 转发 / 预约；充电抽奖自动跳过 |
| 本地 SQLite | `data/binggo.db` 存活动、参与、检查点与任务 |
| 实时进度 | SSE 推送任务进度与日志；断线回退轮询 |
| 定时点击 | 嵌入控制台的调度器；撞车即停，不取消抽奖任务 |
| 结构化日志 | JSONL 日志 + 概览「导出诊断包」（脱敏，无 Cookie / API Key） |
| 配置自检 | 启动检查密钥与绑定；密钥文件尽力收紧权限 |
| 检查更新 | 概览手动检查 GitHub Releases（不自动下载安装） |
| 跨平台分发 | Windows Setup / Portable + macOS arm64 |

设计说明见 [docs/fullstack-roadmap.md](docs/fullstack-roadmap.md)。

---

## Data layout

| 模式 | 数据根目录 |
|------|------------|
| 源码开发 | 仓库根目录 |
| Windows 安装包 | `%APPDATA%\Binggo` |
| Windows 便携（`BINGGO_PORTABLE=1`） | `Binggo.exe` 同目录 |
| macOS 默认 | `~/Library/Application Support/Binggo` |
| macOS 便携（`BINGGO_PORTABLE=1`） | `.app` 所在解压目录 |
| 自定义 | `BINGGO_HOME` |

目录内常见文件：

| 路径 | 用途 |
|------|------|
| `data/binggo.db` | 主库 |
| `data/logs/binggo.log` | JSONL 日志 |
| `config/cookies.txt` | 登录 Cookie |
| `config/llm.env` | LLM 凭证 |
| `config/sources.yaml` | 数据源配置 |

卸载 Windows 程序或删除 `.app` **不会**自动删除数据目录。凭证已在 `.gitignore` 中，请勿提交。

---

## Development

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
| [docs/fullstack-roadmap.md](docs/fullstack-roadmap.md) | 全栈方向总览 |
| [docs/cli.md](docs/cli.md) | CLI 手册 |
| [packaging/windows/README.md](packaging/windows/README.md) | Windows 打包 |
| [packaging/macos/README.md](packaging/macos/README.md) | macOS 打包与 Gatekeeper |
| [web/frontend/README.md](web/frontend/README.md) | 前端开发 |

可选：本地调试用种子导出（**不随发行版分发**）：

```bash
python scripts/export_activities_seed.py
python scripts/export_state_seed.py
```

旧 JSON 活动库若需迁入 SQLite：

```bash
python scripts/import_json_to_db.py
```

---

## Changelog

### v5.0.0（2026-07-20）

**Breaking**

- 发行版**不再**内置活动库种子与数据源 `state` 种子  
- 新安装首次打开活动列表为空；请自行「更新此源」拉取当前有效活动  

**Fullstack（方向 1–9）**

- SQLite 主存储、任务模型持久化、SSE 实时进度  
- API 契约与统一错误体；前端 Vite + TypeScript  
- JSONL 日志、脱敏诊断包、配置自检与密钥治理  
- 手动检查更新；Windows + macOS arm64 安装包；版本号单一来源  

**UX**

- 概览项目信息区排版：元信息面板 + 能力速览  

### Earlier

- **v4.1.0** — 全栈能力首发合集（含预填种子，已在 v5 移除）  
- **v4.0.x** — 定时点击、控制台体验与稳定性  
- **v3.x** — Windows 安装包与开箱体验  

完整历史见 [Releases](https://github.com/luovicter-collab/bilibinggo/releases)。

---

## License

MIT

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=luovicter-collab/bilibinggo&type=Date)](https://star-history.com/#luovicter-collab/bilibinggo&Date)
