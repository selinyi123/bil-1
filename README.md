# Binggo

本地 B 站抽奖助手：从多个 UP 合集与监控用户动态里发现活动，在本机网页控制台一键参与、追踪状态。

[![Release](https://img.shields.io/github/v/release/luovicter-collab/bilibinggo?style=flat-square)](https://github.com/luovicter-collab/bilibinggo/releases/latest)
[![CI](https://img.shields.io/github/actions/workflow/status/luovicter-collab/bilibinggo/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/luovicter-collab/bilibinggo/actions/workflows/ci.yml)
[![Stars](https://img.shields.io/github/stars/luovicter-collab/bilibinggo?style=flat-square)](https://github.com/luovicter-collab/bilibinggo/stargazers)
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

安装包**不再预填**活动或检查点，首次打开活动列表为空，属于正常情况。

| 步骤 | 在哪里 | 做什么 |
|------|--------|--------|
| 1 | 侧栏底部 | **扫码登录**（哔哩哔哩 App） |
| 2 | 概览 → LLM 配置 | 填 API Key / 模型 → **测试连接** → **保存**（玩转发抽奖时需要） |
| 3 | 数据源 → UP 合集 | 对需要的合集点 **「更新此源」**（优先单源；少用「一键更新」） |
| 4 | 活动 | 筛选未参加活动 → 单条参与，或顶部 **「三连参与」** |

可选：在数据源添加常转发抽奖的用户 MID，再点 **「更新监控用户动态」**，补合集漏抓的活动。

运行中任务看右下角 **任务日志**；顶部会出现进度条与结果摘要。

---

## 控制台指南

控制台地址：**http://127.0.0.1:8181**（源码默认多为 `8787`）。左侧三个主页面，右下角两个浮动面板。

### 侧栏

| 控件 | 作用 |
|------|------|
| 概览 / 数据源 / 活动 | 切换主页面 |
| 扫码登录 / 退出 / 刷新账号 | 管理本机 Cookie；未登录时多数任务会提示先登录 |
| 靠边收起 | 收窄侧栏，腾出内容区 |
| 夜间模式 | 切换亮/暗主题（本地记忆） |

### 概览

| 区块 | 作用 |
|------|------|
| 上手引导 | 首次引导登录、LLM、更新源、参与；可跳过 |
| 账号卡片 | 当前登录用户与账号状态 |
| 统计卡片 | 活动数量、参与情况等汇总 |
| 快捷操作 | **更新监控用户动态**、**刷新任务状态**、**一键更新活动链接**、跳转活动列表 |
| 参与文案 | 转发/评论内容：自定义文案，或「随机借用评论」（不足时用兜底文案） |
| LLM 配置 | 解析**转发抽奖**正文（奖品、开奖时间）。互动/预约不耗 LLM。推荐 DeepSeek-V4-Flash |
| 项目信息 | 版本、数据目录、**检查更新**、**导出诊断包**（脱敏，不含 Cookie / API Key）、GitHub 链接 |

说明：

- 「一键更新」会串行扫多个合集，请求更猛，易触发风控；日常请用数据源页的 **「更新此源」**。
- 「刷新任务状态」只刷新本地已有活动的参与/开奖状态，不拉取新链接。

### 数据源

两条发现通道，历史记录本地保留。

**UP 合集**

- 内置多个抽奖合集源；流程：检查新专栏 → 分类 → 拉详情 → 入库（只处理新增链接）。
- **「更新此源」**：只更新这一源，推荐日常使用。
- **「一键更新」**：更新全部合集，适合空库首次灌库，平时慎用。

**监控用户动态**

- 填入用户 **MID**（空间页数字 ID）加入名单。
- **「更新监控用户动态」**：按时间窗口拉取这些人的转发动态，补合集未收录的活动。
- 面板展示监控人数、上次同步、下次窗口与回溯上限（默认约 10 天）。

### 活动

| 功能 | 说明 |
|------|------|
| 类型筛选 | 互动抽奖 / 转发抽奖 / 预约抽奖 |
| 状态筛选 | 未参加 / 已参加 / 已结束 |
| 热度排序 | 按热度升/降序，或默认排序 |
| 即将开奖 | 已参加且约 3 天内开奖 |
| 搜索 | 按奖品名称关键字 |
| 单条参与 | 行内操作：互动走点赞评论等步骤；转发走转发+评论；预约只预约。**充电抽奖自动跳过** |
| 三连参与 | 并行处理当前列表最前 3 个未参加活动 |
| 刷新任务状态 | 回查开奖/参与结果 |

未参加且已过期的活动会从列表隐藏，本地库仍保留历史。

### 浮动面板（全局）

| 面板 | 作用 |
|------|------|
| **任务日志** | 当前/最近 Job 的实时日志（SSE；断线回退轮询） |
| **定时点击** | 嵌入控制台的调度器：到点自动点指定按钮。撞车即停，**不会取消**正在跑的抽奖任务 |

顶部 **进度条** 显示任务百分比与阶段；结束后用结果横幅汇总成功/跳过/失败。

### 推荐日常流程

```text
登录 →（可选）配 LLM → 数据源「更新此源」或更新监控动态
     → 活动筛选「未参加」→ 参与 / 三连
     → 需要时「刷新任务状态」或看「即将开奖」
```

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
